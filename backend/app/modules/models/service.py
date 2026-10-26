"""Điều phối tác vụ tải nền, thư viện model và vòng đời tài nguyên."""

import asyncio
import logging
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.core.errors import SourceError
from app.storage.model_files import ModelFiles

from .catalog.ultralytics import get_variant
from .inspection import ModelInspector
from .repository import ModelRepository, timestamp
from .schemas import DownloadJob, ModelArtifact, StoredModel

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "downloading"}


# ------------------------------- Service model -------------------------------
class ModelService:
    """Chạy lượt tải có giới hạn đồng thời; giữ SQLite và file nhất quán trong một worker.

    Thuộc tính:
        repository: Truy cập metadata và trạng thái tải bền vững.
        files: Storage chỉ quản lý weights, không load PyTorch.
        tasks: Tham chiếu các asyncio task đến khi hoàn tất hoặc shutdown.
    """

    def __init__(self, repository: ModelRepository, settings: Settings) -> None:
        """Nhận repository/settings, dọn lượt bị gián đoạn và mở HTTP client dùng chung."""
        self.max_upload_bytes = settings.max_model_upload_bytes
        self.repository = repository
        root = settings.models_path or settings.sources_path.parent / "models"
        self.files = ModelFiles(root, settings.max_model_bytes)
        self.repository.interrupt()
        self.files.recover()
        self.client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30, connect=15),
            headers={"Accept-Encoding": "identity", "User-Agent": "VisionKit/0.1"},
        )
        self.inspector = ModelInspector(
            repository, self.files, self.client, settings.ai_url
        )
        self.semaphore = asyncio.Semaphore(settings.model_download_concurrency)
        self.lock = asyncio.Lock()
        self.tasks: dict[str, asyncio.Task] = {}
        self.in_use: dict[str, int] = {}
        self.closing = False
        self.cleanup_task: asyncio.Task | None = None

    def available(self, model_id: str) -> StoredModel:
        """Trả model có file còn tồn tại và đúng dung lượng; 404/409 nếu file đã mất/thay đổi.

        Nhận ID trong thư viện và kiểm tra file local; không load weights hoặc
        khẳng định tương thích Ultralytics. Dùng trước khi chọn model cho pipeline.
        Model tạm hết hạn trả 410; model còn hạn được gia hạn thêm 24 giờ trong DB.
        """
        model = self.repository.model(model_id)
        if model is None:
            raise SourceError(404, "Model không còn trong thư viện. Hãy chọn lại.")
        if model.expires_at and model.expires_at <= timestamp():
            raise SourceError(410, "Model tạm đã hết hạn. Hãy chọn lại tệp.")
        self.repository.touch(model_id)
        path = self.files.path(model.location)
        if not path.is_file():
            raise SourceError(
                404, "File model không còn tồn tại. Hãy tải lại hoặc upload lại."
            )
        if path.stat().st_size != model.size_bytes:
            raise SourceError(
                409, "File model đã thay đổi. Hãy tải lại hoặc upload lại."
            )
        return model

    def upload(
        self,
        stream: BinaryIO,
        filename: str,
        name: str | None,
        family: str | None,
        task: str | None,
        temporary: bool = False,
    ) -> StoredModel:
        """Lưu weights riêng và metadata do người dùng khai báo; rollback file nếu DB lỗi.

        Tham số:
            stream: Nội dung nhị phân từ multipart.
            filename: Tên gốc, được loại bỏ mọi thành phần đường dẫn.
            name: Tên hiển thị tuỳ chọn, tối đa 120 ký tự.
            family: yolo hoặc yoloe, không tự suy đoán từ tên file.
            task: Tác vụ đã được router kiểm tra, có thể chưa xác định.
            temporary: True tạo model tạm 24 giờ, False lưu thẳng vào thư viện.
        Trả về:
            Model có UUID riêng, origin upload và checksum của nội dung đã lưu.
        Ngoại lệ:
            SourceError: Tên/loại/tác vụ sai, file rỗng hoặc vượt giới hạn.
            OSError/sqlite3.Error: Không thể lưu file/metadata; dọn file mới nếu lỗi.
        """
        filename = Path(filename.replace("\\", "/")).name
        title = name.strip() if name is not None else filename[:120]
        if not title or len(title) > 120:
            raise SourceError(422, "Tên model phải có từ 1 đến 120 ký tự.")
        if family is not None and family not in ("yolo", "yoloe"):
            raise SourceError(422, "Họ model chưa được hỗ trợ.")
        if family == "yoloe" and task is not None and task != "segment":
            raise SourceError(
                422, "YOLOE dùng tác vụ Segmentation, bao gồm bbox và mask."
            )
        location, size, digest = self.files.save_upload(
            stream, filename, self.max_upload_bytes
        )
        try:
            variant = ModelArtifact(
                id=str(uuid4()),
                familyId=family or "unknown",
                familyName="YOLOE"
                if family == "yoloe"
                else "YOLO"
                if family == "yolo"
                else "Chưa xác định",
                filename=filename,
                task=task,
                format=Path(filename).suffix.lower()[1:],
                name=title,
                origin="upload",
                expected_bytes=size,
                sha256=digest,
            )
            return self.repository.create_uploaded(
                variant, location, size, digest, temporary=temporary
            )
        except Exception:
            self.files.path(location).unlink(missing_ok=True)
            raise

    def get_job(self, job_id: str) -> DownloadJob:
        """Trả trạng thái theo job_id; SourceError 404 nếu lượt tải không tồn tại."""
        job = self.repository.job(job_id)
        if job is None:
            raise SourceError(404, "Không tìm thấy lượt tải model.")
        return job

    async def start(self, catalog_id: str) -> DownloadJob:
        """Tạo hoặc tái sử dụng lượt tải theo ID catalog, trả ngay không chờ tải file.

        Nhận catalog_id đã có trong danh mục; SourceError báo model lạ, đang có sẵn,
        quá dung lượng hoặc hàng chờ đầy. Chỉ tạo task cho lượt mới trong worker.
        """
        variant = get_variant(catalog_id)
        async with self.lock:
            if self.closing:
                raise SourceError(503, "Backend đang dừng. Hãy thử lại.")
            if self.repository.model(catalog_id):
                raise SourceError(
                    409, "Model đã có trong thư viện. Hãy làm mới danh sách."
                )
            if variant.expected_bytes > self.files.max_bytes:
                raise SourceError(
                    413, "Model vượt giới hạn dung lượng tải của backend."
                )
            for active_job in self.repository.jobs():
                if active_job.variant.id == catalog_id and active_job.status in ACTIVE:
                    return active_job
            if len(self.tasks) >= 10:
                raise SourceError(
                    429, "Hàng chờ tải đã đầy. Đợi một lượt hoàn tất rồi thử lại."
                )
            job = self.repository.create_job(variant)
            if job.id not in self.tasks:
                self.tasks[job.id] = asyncio.create_task(self._run(job))
            return job

    async def _report(self, job_id: str, received: int) -> None:
        """Ghi số byte thực nhận cho job_id, không đánh dấu hoàn tất trước khi lưu file."""
        self.repository.update(job_id, "downloading", received)

    async def _transfer(self, job: DownloadJob) -> tuple[str, str]:
        """Tải job bằng storage/client; callback report gắn tiến độ với đúng job ID."""

        async def report(received: int) -> None:
            """Chuyển byte nhận từ storage vào bản ghi download hiện tại."""
            await self._report(job.id, received)

        return await self.files.download(job, self.client, report)

    async def _run(self, job: DownloadJob) -> None:
        """Thực thi job nền tối đa 15 phút; cập nhật lỗi/huỷ và dọn file khi thất bại.

        File được đổi tên trước transaction hoàn tất; nếu DB báo lỗi, file mới
        được dọn. Huỷ khi bàn giao file cũng được dọn trước khi trả trạng thái.
        """
        location = f"{job.id}.pt"
        completed = False
        try:
            async with self.semaphore:
                self.repository.update(job.id, "downloading", 0)
                _, digest = await asyncio.wait_for(self._transfer(job), timeout=900)
                self.repository.complete(job, location, digest)
                completed = True
                try:
                    self.inspector.start(self.available(job.variant.id))
                except Exception:
                    logger.warning(
                        "Weights saved but metadata could not be queued", exc_info=True
                    )
        except asyncio.CancelledError:
            current = self.get_job(job.id)
            self.repository.update(
                job.id,
                "failed" if self.closing else "cancelled",
                current.downloaded_bytes,
                "Tải bị gián đoạn do backend dừng. Hãy thử lại."
                if self.closing
                else None,
            )
        except Exception as error:
            logger.warning("Model download failed: %s", job.id, exc_info=True)
            current = self.get_job(job.id)
            message = (
                error.message
                if isinstance(error, SourceError)
                else "Không tải được model. Kiểm tra kết nối và dung lượng đĩa rồi thử lại."
            )
            self.repository.update(job.id, "failed", current.downloaded_bytes, message)
        finally:
            if not completed:
                self.files.path(location).unlink(missing_ok=True)
                self.files.path(f"{job.id}.part").unlink(missing_ok=True)
            self.tasks.pop(job.id, None)

    async def cancel(self, job_id: str) -> DownloadJob:
        """Huỷ lượt active theo UUID và đợi dọn file; lượt đã kết thúc được giữ nguyên."""
        async with self.lock:
            job = self.get_job(job_id)
            if job.status in ACTIVE:
                task = self.tasks.get(job_id)
                if task:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                self.files.path(f"{job_id}.part").unlink(missing_ok=True)
                current = self.get_job(job_id)
                if current.status in ACTIVE:
                    self.repository.update(
                        job_id, "cancelled", current.downloaded_bytes
                    )
                self.tasks.pop(job_id, None)
            return self.get_job(job_id)

    async def delete(self, model_id: str, expired_only: bool = False) -> None:
        """Xoá bản ghi/file theo model_id, huỷ inspect; khôi phục file nếu DB báo lỗi.

        expired_only=True chỉ xoá model vẫn hết hạn tại thời điểm giữ lock,
        bỏ qua model đã được lưu hoặc gia hạn. Xoá thường trả 404 nếu ID không có.
        """
        async with self.lock:
            model = self.repository.model(model_id)
            if self.in_use.get(model_id, 0):
                if expired_only:
                    return
                raise SourceError(
                    409, "Model đang dùng trong lượt chạy. Hãy dừng trước khi xoá."
                )
            if expired_only and (
                model is None or not model.expires_at or model.expires_at > timestamp()
            ):
                return
            await self.inspector.cancel(model_id)
            if model is None:
                raise SourceError(404, "Không tìm thấy model đã lưu.")
            path = self.files.path(model.location)
            temporary = path.with_suffix(".trash")
            exists = path.is_file()
            if exists:
                path.replace(temporary)
            try:
                self.repository.delete(model_id)
            except Exception:
                if exists:
                    temporary.replace(path)
                raise
            temporary.unlink(missing_ok=True)

    async def promote(self, model_id: str, name: str) -> StoredModel:
        """Lưu model tạm còn hạn vào thư viện, đồng bộ với cleanup để không xoá nhầm file."""
        title = name.strip()
        if not title or len(title) > 120:
            raise SourceError(422, "Tên model phải có từ 1 đến 120 ký tự.")
        async with self.lock:
            self.available(model_id)
            return self.repository.promote(model_id, title)

    async def cleanup_temporary(self) -> None:
        """Dọn model tạm hết hạn cùng task inspect; giữ nguyên model đã gia hạn hoặc lưu thư viện."""
        for model_id in self.repository.expired_ids():
            await self.delete(model_id, expired_only=True)

    async def maintain_temporary(self) -> None:
        """Dọn model hết hạn mỗi 10 phút đến khi shutdown; ghi log lỗi để vòng dọn vẫn tiếp tục."""
        while True:
            await asyncio.sleep(600)
            try:
                await self.cleanup_temporary()
            except Exception:
                logger.warning("Temporary model cleanup failed", exc_info=True)

    async def shutdown(self) -> None:
        """Dừng mọi task nền, ghi trạng thái gián đoạn và đóng HTTP client khi app dừng."""
        self.closing = True
        if self.cleanup_task:
            self.cleanup_task.cancel()
            await asyncio.gather(self.cleanup_task, return_exceptions=True)
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.repository.interrupt()
        self.files.recover()
        self.tasks.clear()
        await self.inspector.close()
        await self.client.aclose()
