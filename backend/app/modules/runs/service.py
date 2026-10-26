"""Điều phối lượt inference ảnh; backend quản lý file/DB và gọi AI qua HTTP."""

import asyncio
import json
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import httpx
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import SourceError
from app.modules.models.repository import timestamp
from app.modules.models.schemas import StoredModel
from app.modules.models.service import ModelService
from app.storage.local import LocalStorage

from .repository import RunRepository
from .schemas import RunOptions, RunRecord


# ------------------------------- Service lượt chạy ---------------------------
class RunService:
    """Giữ tối đa bốn lượt active và một request inference đồng thời; bảo vệ model đang dùng."""

    def __init__(
        self, repository: RunRepository, models: ModelService, settings: Settings
    ) -> None:
        """Tạo storage/client riêng và đánh dấu job gián đoạn; không import module AI."""
        self.repository = repository
        self.models = models
        self.settings = settings
        self.storage = LocalStorage(
            replace(
                settings,
                sources_path=settings.runs_path
                or settings.sources_path.parent / "runs",
            )
        )
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(210, connect=5))
        self.tasks: dict[str, asyncio.Task] = {}
        self.pinned: dict[str, str] = {}
        self.latest: dict[str, RunRecord] = {}
        self.semaphore = asyncio.Semaphore(1)
        self.repository.interrupt()
        self.cleanup_task: asyncio.Task | None = None
        self.cleanup_expired()

    def get(self, run_id: str) -> RunRecord:
        """Trả bản ghi chạy hoặc lỗi 404; không khởi động lại inference."""
        record = self.latest.get(run_id) or self.repository.get(run_id)
        if record is None:
            raise SourceError(404, "Không tìm thấy lượt chạy.")
        if record.expires_at <= timestamp() and record.status not in {
            "queued",
            "running",
        }:
            raise SourceError(410, "Lượt chạy đã hết hạn. Hãy chạy lại.")
        return record

    async def create(
        self,
        model_id: str,
        options: RunOptions,
        stream: BinaryIO,
        filename: str,
        kind: str = "image",
    ) -> RunRecord:
        """Lưu ảnh độc lập thư viện rồi tạo job; rollback file nếu model/cấu hình/DB không hợp lệ."""
        if not self.settings.ai_url:
            raise SourceError(503, "AI chưa được cấu hình.")
        if len(self.tasks) >= 4:
            raise SourceError(429, "Hàng chờ chạy đã đầy.")
        location, metadata = await run_in_threadpool(
            self.storage.save_video if kind == "video" else self.storage.save_image,
            stream,
            filename,
        )
        try:
            async with self.models.lock:
                if len(self.tasks) >= 4:
                    raise SourceError(429, "Hàng chờ chạy đã đầy.")
                model = self.models.available(model_id)
                if model.inspection.status not in {"ready", "manual"}:
                    raise SourceError(409, "Đọc metadata model trước khi chạy.")
                if model.variant.task not in {
                    "detect",
                    "pose",
                    "classify",
                    "segment",
                    "obb",
                }:
                    raise SourceError(422, "Tác vụ model chưa được hỗ trợ.")
                if any(size < 32 or size > 4096 for size in options.imgsz):
                    raise SourceError(422, "Kích thước đầu vào không hợp lệ.")
                names = (
                    model.inspection.metadata.names if model.inspection.metadata else {}
                )
                if options.classes is not None and (
                    not options.classes
                    or any(str(index) not in names for index in options.classes)
                ):
                    raise SourceError(422, "Danh sách class không hợp lệ.")
                run_id = str(uuid4())
                record = self.repository.save(
                    RunRecord(
                        id=run_id,
                        status="queued",
                        source_kind=kind,
                        model_id=model_id,
                        source_location=location,
                        source_metadata=metadata,
                        options=options,
                        expires_at=(
                            datetime.now(timezone.utc) + timedelta(hours=24)
                        ).isoformat(),
                        created_at=timestamp(),
                        updated_at=timestamp(),
                    )
                )
                self.models.in_use[model_id] = self.models.in_use.get(model_id, 0) + 1
                self.pinned[run_id] = model_id
                self.tasks[run_id] = asyncio.create_task(
                    self._run(record, model), name=run_id
                )
                self.tasks[run_id].add_done_callback(self._finished)
                return record
        except Exception:
            for path in self.storage.source_paths(location, metadata):
                path.unlink(missing_ok=True)
            raise

    async def _run(self, record: RunRecord, model: StoredModel) -> None:
        """Gọi AI, xác minh JSON cơ bản và lưu kết quả; huỷ request khi người dùng dừng."""
        try:
            async with self.semaphore:
                self.repository.save(record.model_copy(update={"status": "running"}))
                if record.source_kind == "video":
                    await self._video(record, model)
                    return
                response = await self.client.post(
                    f"{self.settings.ai_url}/api/v1/inference/image",
                    json={
                        "model_location": model.location,
                        "model_sha256": model.sha256,
                        "source_location": record.source_location,
                        "source_sha256": record.source_metadata["sha256"],
                        "family": "yoloe"
                        if model.variant.familyId.startswith("yoloe")
                        else "yolo",
                        "task": model.variant.task,
                        "options": record.options.model_dump(),
                    },
                )
                if response.status_code == 422:
                    detail = response.json().get("detail")
                    raise SourceError(
                        422,
                        detail
                        if isinstance(detail, str)
                        else "Thông số inference không hợp lệ.",
                    )
                response.raise_for_status()
                result = response.json()
                if not isinstance(result.get("detections"), list) or not isinstance(
                    result.get("sourceSize"), dict
                ):
                    raise ValueError("AI response không hợp lệ")
                self.repository.save(
                    record.model_copy(update={"status": "completed", "result": result})
                )
        except asyncio.CancelledError:
            current = self.latest.get(record.id) or record
            self.repository.save(current.model_copy(update={"status": "cancelled"}))
        except Exception as error:
            message = (
                error.message
                if isinstance(error, SourceError)
                else "Không chạy được inference. Kiểm tra kết nối AI và thử lại."
            )
            self.repository.save(
                (self.latest.get(record.id) or record).model_copy(
                    update={"status": "failed", "error": message}
                )
            )
        finally:
            self.latest.pop(record.id, None)
            self._release(record.id)

    async def _video(self, record: RunRecord, model: StoredModel) -> None:
        """Đọc event video tuần tự, giữ một snapshot mới nhất và ghi DB tối đa mỗi giây.

        Không lưu timeline hoặc xếp hàng kết quả cho trình duyệt. Chỉ completed
        khi nhận terminal event; EOF sớm hoặc event error giữ lại kết quả cuối.
        """
        payload = {
            "model_location": model.location,
            "model_sha256": model.sha256,
            "source_location": record.source_location,
            "source_sha256": record.source_metadata["sha256"],
            "family": "yoloe" if model.variant.familyId.startswith("yoloe") else "yolo",
            "task": model.variant.task,
            "options": record.options.model_dump(),
        }
        last_write = 0.0
        completed = False
        async with self.client.stream(
            "POST", f"{self.settings.ai_url}/api/v1/inference/video", json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                if len(line) > 8 * 1024 * 1024:
                    raise SourceError(502, "Kết quả frame video quá lớn.")
                event = json.loads(line)
                if event.get("type") == "error":
                    raise SourceError(
                        422, str(event.get("error", "Không chạy được video."))[:250]
                    )
                if event.get("type") not in {"frame", "completed"}:
                    raise SourceError(502, "Sự kiện AI không hợp lệ.")
                result = event.get("result")
                if (
                    not isinstance(result, dict)
                    or not isinstance(result.get("detections"), list)
                    or not isinstance(result.get("sourceSize"), dict)
                ):
                    raise SourceError(502, "Kết quả video không hợp lệ.")
                completed = event["type"] == "completed"
                current = record.model_copy(
                    update={
                        "status": "completed" if completed else "running",
                        "result": result,
                        "progress": event.get("progress"),
                        "updated_at": timestamp(),
                    }
                )
                self.latest[record.id] = current
                if completed or time.monotonic() - last_write >= 1:
                    self.repository.save(current)
                    last_write = time.monotonic()
                if completed:
                    break
        if not completed:
            raise SourceError(502, "Luồng kết quả video bị gián đoạn.")

    def _release(self, run_id: str) -> None:
        """Giải phóng lease đúng một lần, kể cả huỷ task trước khi coroutine bắt đầu."""
        model_id = self.pinned.pop(run_id, None)
        if model_id:
            self.models.in_use[model_id] = max(
                0, self.models.in_use.get(model_id, 1) - 1
            )
        self.tasks.pop(run_id, None)

    def _finished(self, task: asyncio.Task) -> None:
        """Dọn task/lease và ghi cancelled nếu task chưa kịp chạy thân coroutine."""
        run_id = task.get_name()
        record = self.repository.get(run_id)
        if task.cancelled() and record and record.status in {"queued", "running"}:
            current = self.latest.get(record.id) or record
            self.repository.save(current.model_copy(update={"status": "cancelled"}))
        self._release(run_id)

    async def cancel(self, run_id: str) -> RunRecord:
        """Huỷ job active và đợi ghi trạng thái; giữ ảnh đầu vào để xem lại."""
        record = self.get(run_id)
        task = self.tasks.get(run_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.get(record.id)

    def content(self, run_id: str) -> Path:
        """Trả ảnh preview phù hợp trình duyệt trong storage riêng của lượt chạy."""
        record = self.get(run_id)
        location = (
            record.source_location
            if record.source_kind == "video"
            else record.source_metadata.get("preview_location", record.source_location)
        )
        path = self.storage.path(location)
        if not path.is_file():
            raise SourceError(404, "Ảnh lượt chạy không còn tồn tại.")
        return path

    def cleanup_expired(self) -> None:
        """Xoá ảnh snapshot và JSON kết quả terminal hết hạn 24 giờ; không chạm source thư viện."""
        for record in self.repository.expired():
            for path in self.storage.source_paths(
                record.source_location, record.source_metadata
            ):
                path.unlink(missing_ok=True)
            self.repository.delete(record.id)

    async def maintain(self) -> None:
        """Dọn snapshot hết hạn mỗi 10 phút; không huỷ lượt inference còn active."""
        while True:
            await asyncio.sleep(600)
            try:
                self.cleanup_expired()
            except OSError:
                pass

    async def shutdown(self) -> None:
        """Huỷ job nền và đóng HTTP client trước khi backend dừng."""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            await asyncio.gather(self.cleanup_task, return_exceptions=True)
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.client.aclose()
