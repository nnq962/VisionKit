"""Điều phối lượt inference ảnh; backend quản lý file/DB và gọi AI qua HTTP."""

import asyncio
import json
import logging
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import anyio
import httpx
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import SourceError
from app.core.logs import run_context
from app.core.rtsp import validate_rtsp_url
from app.modules.models.repository import timestamp
from app.modules.models.schemas import StoredModel
from app.modules.models.service import ModelService
from app.modules.sources.models import Source, SourceKind
from app.modules.streams.service import PreviewService
from app.storage.local import LocalStorage

from .repository import RunRepository
from .schemas import RunOptions, RunRecord

logger = logging.getLogger(__name__)


# ------------------------------- Service lượt chạy ---------------------------
class RunService:
    """Giữ tối đa bốn lượt active và một request inference đồng thời; bảo vệ model đang dùng."""

    def __init__(
        self,
        repository: RunRepository,
        models: ModelService,
        settings: Settings,
        previews: PreviewService | None = None,
    ) -> None:
        """Tạo storage/client riêng và đánh dấu job gián đoạn; không import module AI."""
        self.previews = previews
        self.relay_leases: dict[str, str] = {}
        self.release_tasks: set[asyncio.Task] = set()
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
            return await self._enqueue(model_id, options, location, metadata, kind)
        except Exception:
            for path in self.storage.source_paths(location, metadata):
                path.unlink(missing_ok=True)
            raise

    async def create_live(
        self,
        model_id: str,
        options: RunOptions,
        source_id: str | None,
        preview_id: str | None,
        duration_seconds: int,
    ) -> RunRecord:
        """Chạy AI đọc MediaMTX, giữ path đến khi terminal; không lưu URL camera trong run."""
        if self.previews is None:
            raise SourceError(503, "Relay chưa được cấu hình.")
        token, relay = await self.previews.acquire_inference(source_id, preview_id)
        try:
            record = await self._enqueue(
                model_id,
                options,
                "",
                {
                    "source_id": source_id,
                    "preview_id": preview_id,
                    "is_live": True,
                    "preview_available": False,
                    "via_mediamtx": True,
                    "duration_seconds": duration_seconds,
                },
                "stream",
                stream_url=relay,
                duration_seconds=duration_seconds,
            )
            self.relay_leases[record.id] = token
            return record
        except BaseException:
            with anyio.CancelScope(shield=True):
                await self.previews.close(token)
            raise

    async def create_stream(
        self, model_id: str, options: RunOptions, source: Source, duration_seconds: int
    ) -> RunRecord:
        """Tạo live job bằng source đã lưu; URL thật chỉ giữ trong task, không ghi record/log.

        Không tạo file snapshot. Lượt chạy có hạn rõ ràng và phải dừng bằng API cancel
        hoặc hoàn tất khi đến hạn; chỉnh/xoá source không đổi snapshot URL của task.
        """
        if source.kind != SourceKind.STREAM:
            raise SourceError(422, "Chọn source RTSP đã lưu.")
        try:
            url = validate_rtsp_url(source.location)
        except ValueError:
            raise SourceError(422, "Source không có URL RTSP hợp lệ.") from None
        return await self._enqueue(
            model_id,
            options,
            "",
            {
                "source_id": source.id,
                "is_live": True,
                "preview_available": False,
                "duration_seconds": duration_seconds,
            },
            "stream",
            stream_url=url,
            duration_seconds=duration_seconds,
        )

    async def _enqueue(
        self,
        model_id: str,
        options: RunOptions,
        location: str,
        metadata: dict,
        kind: str,
        *,
        stream_url: str | None = None,
        duration_seconds: int = 3600,
    ) -> RunRecord:
        """Kiểm model/options và giữ lease trong cùng khoá trước khi đưa job vào hàng chờ."""
        if not self.settings.ai_url:
            raise SourceError(503, "AI chưa được cấu hình.")
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
            names = model.inspection.metadata.names if model.inspection.metadata else {}
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
                self._run(
                    record,
                    model,
                    stream_url=stream_url,
                    duration_seconds=duration_seconds,
                ),
                name=run_id,
            )
            self.tasks[run_id].add_done_callback(self._finished)
            logger.info("Đã tạo lượt chạy %s.", kind, extra={"run_id": run_id})
            return record

    async def _run(
        self,
        record: RunRecord,
        model: StoredModel,
        *,
        stream_url: str | None = None,
        duration_seconds: int = 3600,
    ) -> None:
        """Gọi AI, xác minh JSON cơ bản và lưu kết quả; huỷ request khi người dùng dừng."""
        token = run_context.set(record.id)
        try:
            async with self.semaphore:
                logger.info("Bắt đầu xử lý %s.", record.source_kind)
                self.repository.save(record.model_copy(update={"status": "running"}))
                if record.source_kind in {"video", "stream"}:
                    await self._video(
                        record,
                        model,
                        stream_url=stream_url,
                        duration_seconds=duration_seconds,
                    )
                    return
                response = await self.client.post(
                    f"{self.settings.ai_url}/api/v1/inference/image",
                    headers={"X-VisionKit-Run-ID": record.id},
                    json={
                        "model_location": model.location,
                        "model_sha256": model.sha256,
                        "source_location": record.source_location,
                        "source_sha256": record.source_metadata.get("sha256"),
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
                logger.info("Hoàn tất inference ảnh.")
        except asyncio.CancelledError:
            logger.info("Đã huỷ lượt chạy.")
            current = self.latest.get(record.id) or record
            self.repository.save(current.model_copy(update={"status": "cancelled"}))
        except Exception as error:
            logger.exception("Lượt chạy thất bại.")
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
            run_context.reset(token)

    async def _video(
        self,
        record: RunRecord,
        model: StoredModel,
        *,
        stream_url: str | None = None,
        duration_seconds: int = 3600,
    ) -> None:
        """Đọc event video/live, giữ một snapshot mới nhất và ghi DB tối đa mỗi giây.

        Không lưu timeline hoặc xếp hàng kết quả cho trình duyệt. Chỉ completed
        khi nhận terminal event; EOF sớm hoặc event error giữ lại kết quả cuối.
        """
        payload = {
            "model_location": model.location,
            "model_sha256": model.sha256,
            "source_location": record.source_location,
            "source_sha256": record.source_metadata.get("sha256"),
            "family": "yoloe" if model.variant.familyId.startswith("yoloe") else "yolo",
            "task": model.variant.task,
            "options": record.options.model_dump(),
        }
        endpoint = "video"
        if record.source_kind == "stream":
            endpoint = "stream"
            payload.pop("source_location")
            payload.pop("source_sha256")
            payload.update(stream_url=stream_url, duration_seconds=duration_seconds)
        last_write = 0.0
        last_log = time.monotonic()
        completed = False
        async with self.client.stream(
            "POST",
            f"{self.settings.ai_url}/api/v1/inference/{endpoint}",
            json=payload,
            headers={"X-VisionKit-Run-ID": record.id},
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
                        422,
                        "Không xử lý được stream. Kiểm tra camera và kết nối."
                        if record.source_kind == "stream"
                        else str(event.get("error", "Không chạy được video."))[:250],
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
                if (
                    completed
                    and record.source_kind == "stream"
                    and event.get("reason") != "duration_limit"
                ):
                    raise SourceError(502, "Stream kết thúc thiếu lý do hợp lệ.")
                current = record.model_copy(
                    update={
                        "status": "completed" if completed else "running",
                        "result": result,
                        "progress": event.get("progress"),
                        "completion_reason": "duration_limit"
                        if completed and record.source_kind == "stream"
                        else None,
                        "updated_at": timestamp(),
                    }
                )
                self.latest[record.id] = current
                if completed or time.monotonic() - last_write >= 1:
                    self.repository.save(current)
                    last_write = time.monotonic()
                if completed or time.monotonic() - last_log >= 5:
                    progress = event.get("progress") or {}
                    logger.info(
                        "%s video: %s frame, %s FPS.",
                        "Hoàn tất" if completed else "Đang xử lý",
                        progress.get("frames_processed", "?"),
                        progress.get("processing_fps", "?"),
                    )
                    last_log = time.monotonic()
                if completed:
                    break
        if not completed:
            raise SourceError(502, "Luồng kết quả video bị gián đoạn.")

    def _release(self, run_id: str) -> None:
        """Giải phóng lease đúng một lần, kể cả huỷ task trước khi coroutine bắt đầu."""
        relay = self.relay_leases.pop(run_id, None)
        if relay and self.previews:
            task = asyncio.create_task(self.previews.close(relay))
            self.release_tasks.add(task)
            task.add_done_callback(self.release_tasks.discard)
        model_id = self.pinned.pop(run_id, None)
        if model_id:
            remaining = self.models.in_use.get(model_id, 1) - 1
            if remaining > 0:
                self.models.in_use[model_id] = remaining
            else:
                self.models.in_use.pop(model_id, None)
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
        if self.release_tasks:
            await asyncio.gather(*tuple(self.release_tasks), return_exceptions=True)
        return self.get(record.id)

    def content(self, run_id: str) -> Path:
        """Trả ảnh preview phù hợp trình duyệt trong storage riêng của lượt chạy."""
        record = self.get(run_id)
        if record.source_kind == "stream":
            raise SourceError(404, "Stream chưa có preview trên trình duyệt.")
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
            if record.source_kind != "stream":
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
        if self.release_tasks:
            await asyncio.gather(*tuple(self.release_tasks), return_exceptions=True)
        await self.client.aclose()
