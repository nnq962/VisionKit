"""Gọi API AI và lưu tiến độ đọc metadata, độc lập với logic inference."""

import asyncio
import logging

import httpx

from app.storage.model_files import ModelFiles

from .repository import ModelRepository
from .schemas import ModelInspection, StoredModel

logger = logging.getLogger(__name__)


# ----------------------------- Điều phối inspect -----------------------------
class ModelInspector:
    """Quản lý tác vụ đọc metadata nền; backend chỉ gửi đường dẫn tương đối và checksum."""

    def __init__(
        self,
        repository: ModelRepository,
        files: ModelFiles,
        client: httpx.AsyncClient,
        ai_url: str | None,
    ) -> None:
        """Giữ repo/storage/client dùng chung và URL AI; khôi phục trạng thái lượt bị gián đoạn."""
        self.repository = repository
        self.files = files
        self.client = client
        self.ai_url = ai_url
        self.tasks: dict[str, asyncio.Task] = {}
        self.semaphore = asyncio.Semaphore(1)
        self.closing = False
        self.repository.interrupt_inspections()

    def start(self, model: StoredModel) -> StoredModel:
        """Đánh dấu queued và tạo task cho model đã lưu; trùng lượt trả trạng thái hiện tại.

        Khi AI chưa cấu hình, đang dừng hoặc hàng chờ đầy, giữ file/bản ghi và
        đánh dấu unavailable để người dùng có thể thử lại, không báo upload thất bại.
        """
        if model.id in self.tasks:
            return self.repository.model(model.id) or model
        if not self.ai_url or self.closing or len(self.tasks) >= 10:
            result = ModelInspection(
                status="unavailable",
                message="AI chưa sẵn sàng hoặc đang bận. Hãy thử đọc metadata lại.",
            )
            return self.repository.set_inspection(model.id, result) or model
        result = ModelInspection(status="queued")
        updated = self.repository.set_inspection(model.id, result) or model
        self.tasks[model.id] = asyncio.create_task(self._run(updated))
        return updated

    async def _run(self, model: StoredModel) -> None:
        """Gọi inspect nội bộ với timeout, xác thực response và ghi metadata vào SQLite.

        Chỉ chuyển trạng thái ready từ response AI hợp lệ; lỗi kết nối không xoá
        model đã upload. Kết quả muộn sau khi xoá model không tạo lại bản ghi.
        """
        try:
            async with self.semaphore:
                self.repository.set_inspection(
                    model.id, ModelInspection(status="processing")
                )
                response = await self.client.post(
                    f"{self.ai_url}/api/v1/models/inspect",
                    json={"location": model.location, "sha256": model.sha256},
                    timeout=httpx.Timeout(110, connect=5),
                )
                response.raise_for_status()
                result = ModelInspection.model_validate(response.json())
                if result.status not in {"ready", "needs_input", "failed"} or (
                    result.status != "failed" and result.metadata is None
                ):
                    raise ValueError("AI trả trạng thái không hợp lệ")
                if result.metadata and result.metadata.format != model.variant.format:
                    raise ValueError("AI trả định dạng không khớp file")
                if result.status == "ready" and (
                    not result.metadata.family or not result.metadata.task
                ):
                    raise ValueError("AI thiếu family/task nhưng báo ready")
                self.repository.set_inspection(model.id, result)
        except asyncio.CancelledError:
            self.repository.set_inspection(
                model.id,
                ModelInspection(
                    status="unavailable",
                    message="Đọc metadata bị gián đoạn. Hãy thử lại.",
                ),
            )
        except Exception:
            logger.warning("AI metadata request failed for %s", model.id, exc_info=True)
            self.repository.set_inspection(
                model.id,
                ModelInspection(
                    status="unavailable",
                    message="Không kết nối được AI để đọc metadata. Hãy thử lại.",
                ),
            )
        finally:
            self.tasks.pop(model.id, None)

    async def cancel(self, model_id: str) -> None:
        """Huỷ task của model_id trước khi xoá model; không tác động lượt tải weights."""
        task = self.tasks.get(model_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        """Huỷ mọi task inspect khi app dừng và ghi trạng thái gián đoạn trước khi đóng client."""
        self.closing = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.repository.interrupt_inspections()
        self.tasks.clear()
