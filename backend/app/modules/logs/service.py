"""Thu log AI qua HTTP nền; không gắn việc thu log vào đường chạy inference."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.core.logs import LogBuffer, LogPage

logger = logging.getLogger(__name__)


# ------------------------------- Bộ thu log AI -------------------------------
class LogCollector:
    """Gom log AI vào bộ đệm backend bằng một task duy nhất, không có hàng đợi vô hạn."""

    def __init__(self, buffer: LogBuffer, ai_url: str | None) -> None:
        """Giữ đích nội bộ cố định, cursor riêng và trạng thái kết nối ban đầu."""
        self.buffer = buffer
        self.ai_url = ai_url
        self.cursor: str | None = None
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(2, connect=1))
        self.status: dict = {
            "configured": bool(ai_url),
            "available": None,
            "last_success_at": None,
            "reset_count": 0,
            "dropped_batches": 0,
        }

    async def collect(self) -> None:
        """Lấy tối đa bốn trang mỗi lượt, xác thực dữ liệu và tiến cursor sau khi nhập.

        Lỗi mạng/response giữ nguyên cursor để lần sau thử lại. Trạng thái AI
        nằm ngoài stream log; mất AI không ngăn đọc log backend.
        """
        if not self.ai_url:
            return
        try:
            for _ in range(4):
                params = {"limit": 500}
                if self.cursor:
                    params["after"] = self.cursor
                response = await self.client.get(
                    f"{self.ai_url}/api/v1/logs", params=params
                )
                response.raise_for_status()
                page = LogPage.model_validate(response.json())
                if any(item.service != "ai" for item in page.items):
                    raise ValueError("Nguồn AI trả log sai dịch vụ.")
                for item in page.items:
                    self.buffer.append(
                        item.level,
                        item.message,
                        item.logger,
                        item.run_id,
                        item.traceback,
                        original=item,
                    )
                self.cursor = page.next_cursor
                self.status["reset_count"] += int(page.reset)
                self.status["dropped_batches"] += int(page.dropped)
                if not page.has_more:
                    break
            was_unavailable = self.status["available"] is False
            self.status["available"] = True
            self.status["last_success_at"] = datetime.now(timezone.utc).isoformat()
            if was_unavailable:
                logger.info("Kết nối thu log AI đã phục hồi.")
        except (httpx.HTTPError, ValueError, TypeError):
            if self.status["available"] is not False:
                logger.warning("Không lấy được log AI; sẽ tự thử lại.")
            self.status["available"] = False

    async def run(self) -> None:
        """Thu mỗi giây tới khi task bị huỷ; không tạo request theo từng trình duyệt."""
        while True:
            await self.collect()
            await asyncio.sleep(1)

    async def close(self) -> None:
        """Đóng pool HTTP sau khi task thu log đã được huỷ và đợi kết thúc."""
        await self.client.aclose()
