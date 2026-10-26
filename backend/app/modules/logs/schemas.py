"""Hợp đồng API log chung cho web, gồm trạng thái nguồn AI độc lập với log backend."""

from pydantic import BaseModel

from app.core.logs import LogPage


# ---------------------------- Trạng thái thu AI ------------------------------
class AiLogStatus(BaseModel):
    """Phân biệt chưa kết nối, offline và các lần mất lịch sử tại nguồn AI."""

    configured: bool
    available: bool | None
    last_success_at: str | None
    reset_count: int
    dropped_batches: int


# ---------------------------- Trang log tập trung ----------------------------
class CombinedLogPage(LogPage):
    """Trả log theo thứ tự backend tiếp nhận và trạng thái thu nguồn AI."""

    ai: AiLogStatus
