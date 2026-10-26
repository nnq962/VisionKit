"""Thu log Python vào bộ đệm RAM hữu hạn, đọc tăng dần bằng cursor theo phiên."""

import logging
import re
import threading
import traceback
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

run_context: ContextVar[str | None] = ContextVar("log_run_id", default=None)
LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SECRETS = re.compile(
    r"(?i)(authorization\s*[:=]\s*(?:bearer\s+|basic\s+)?|"
    r"(?:password|api[_-]?key|access[_-]?token|secret)\s*[=:]\s*)[^\s,;]+"
)


# -------------------------------- Bản ghi log --------------------------------
class LogEntry(BaseModel):
    """Giữ log đã giới hạn kích thước; id thể hiện thứ tự nhận tại dịch vụ gom log."""

    id: str = Field(pattern=r"^[a-f0-9]{32}:[0-9]{1,20}$")
    timestamp: str
    service: Literal["backend", "ai"]
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    logger: str
    message: str
    run_id: str | None = None
    traceback: str | None = None
    source_id: str | None = None


# --------------------------------- Trang log ---------------------------------
class LogPage(BaseModel):
    """Trả cursor kế tiếp và dấu hiệu mất lịch sử; không suy diễn liên tục sau restart."""

    items: list[LogEntry]
    next_cursor: str = Field(pattern=r"^[a-f0-9]{32}:[0-9]{1,20}$")
    has_more: bool
    reset: bool
    dropped: bool


# ----------------------------- Làm sạch nội dung -----------------------------
def clean_text(value: str) -> str:
    """Bỏ mã màu/ký tự điều khiển, che một số credential phổ biến và cắt tối đa 8192 ký tự.

    Không thay thế cơ chế bảo mật: bên gọi không được chủ động ghi token hoặc
    nội dung file vào log. Giữ xuống dòng/tab để đọc traceback.
    """
    value = ANSI.sub("", value[:32768])
    value = "".join(char for char in value if char in "\n\t" or ord(char) >= 32)
    return SECRETS.sub(r"\1[REDACTED]", value)[:8192]


# -------------------------------- Bộ đệm log ---------------------------------
class LogBuffer:
    """Giữ tối đa capacity bản ghi trong một process; thread-safe, không ghi DB/file.

    Cursor chứa epoch và số thứ tự; lọc vẫn tiến cursor qua các bản ghi đã xét.
    Khi ghi đè hoặc restart, response báo dropped/reset để client hiển thị khoảng trống.
    """

    def __init__(self, service: str, capacity: int = 2000) -> None:
        """Khởi tạo phiên và deque hữu hạn cho tên dịch vụ được chỉ định."""
        if capacity < 1:
            raise ValueError("Dung lượng log phải lớn hơn 0.")
        self.service = service
        self.epoch = uuid4().hex
        self.sequence = 0
        self.entries: deque[tuple[int, LogEntry]] = deque(maxlen=capacity)
        self.lock = threading.Lock()

    def append(
        self,
        level: str,
        message: str,
        logger: str = "app",
        run_id: str | None = None,
        trace: str | None = None,
        original: LogEntry | None = None,
    ) -> None:
        """Thêm một log hoặc nhập log AI; giới hạn nội dung và cấp id mới trong lock.

        original giữ timestamp/service/id gốc khi backend gom log AI. Không gọi
        mạng hoặc filesystem; log cũ nhất tự rời bộ đệm khi đầy.
        """
        with self.lock:
            self.sequence += 1
            entry = LogEntry(
                id=f"{self.epoch}:{self.sequence}",
                timestamp=original.timestamp
                if original
                else datetime.now(timezone.utc).isoformat(),
                service=original.service if original else self.service,
                level=level if level in LEVELS else "INFO",
                logger=clean_text(logger)[:200],
                message=clean_text(message),
                run_id=run_id,
                traceback=clean_text(trace) if trace else None,
                source_id=original.id if original else None,
            )
            self.entries.append((self.sequence, entry))

    def read(
        self,
        after: str | None = None,
        limit: int = 200,
        service: str | None = None,
        min_level: str = "INFO",
        run_id: str | None = None,
    ) -> LogPage:
        """Đọc tối đa limit log phù hợp sau cursor; ném ValueError nếu cursor sai cú pháp.

        has_more cho biết còn bản ghi chưa xét. next_cursor phải được dùng nguyên
        vẹn; đổi bộ lọc cần bắt đầu lại bằng after=None.
        """
        if not 1 <= limit <= 500 or min_level not in LEVELS:
            raise ValueError("Giới hạn hoặc mức log không hợp lệ.")
        epoch, position = self.epoch, 0
        if after:
            if not re.fullmatch(r"[a-f0-9]{32}:[0-9]{1,20}", after):
                raise ValueError("Cursor log không hợp lệ.")
            epoch, number = after.split(":")
            position = int(number)
        with self.lock:
            entries = list(self.entries)
            end = self.sequence
        reset = bool(after and (epoch != self.epoch or position > end))
        if reset:
            position = 0
        oldest = entries[0][0] if entries else end + 1
        dropped = bool(after and not reset and position < oldest - 1)
        items: list[LogEntry] = []
        scanned = max(position, oldest - 1)
        for sequence, entry in entries:
            if sequence <= position:
                continue
            scanned = sequence
            if (
                (service is None or service == entry.service)
                and LEVELS.get(entry.level, 20) >= LEVELS[min_level]
                and (run_id is None or run_id == entry.run_id)
            ):
                items.append(entry)
                if len(items) >= limit:
                    break
        return LogPage(
            items=items,
            next_cursor=f"{self.epoch}:{scanned}",
            has_more=scanned < end,
            reset=reset,
            dropped=dropped,
        )


# ------------------------------ Handler bộ đệm -------------------------------
class BufferHandler(logging.Handler):
    """Sao chép log ứng dụng/Uvicorn vào RAM, giữ nguyên handler terminal hiện có."""

    def __init__(self, buffer: LogBuffer) -> None:
        """Gắn bộ đệm đích và nhận log từ INFO trở lên."""
        super().__init__(logging.INFO)
        self.buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        """Định dạng log/traceback, bỏ access log health/logs để không tự sinh vòng lặp."""
        try:
            message = record.getMessage()
            if record.name == "uvicorn.access" and any(
                path in message for path in ("/api/v1/logs", "/api/v1/health")
            ):
                return
            trace = (
                "".join(traceback.format_exception(*record.exc_info))
                if record.exc_info
                else getattr(record, "worker_traceback", None)
            )
            self.buffer.append(
                record.levelname,
                message,
                record.name,
                getattr(record, "run_id", None) or run_context.get(),
                trace,
            )
        except Exception:
            # Log hỏng không được làm gián đoạn request/inference.
            return


# ---------------------------- Cài đặt handler tạm ----------------------------
def attach_logging(
    buffer: LogBuffer,
) -> list[tuple[logging.Logger, int, BufferHandler]]:
    """Gắn handler vào app/Uvicorn; trả cấu hình cũ để khôi phục khi lifespan đóng."""
    attached = []
    for name in ("app", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        handler = BufferHandler(buffer)
        attached.append((logger, logger.level, handler))
        logger.addHandler(handler)
        if logger.getEffectiveLevel() > logging.INFO:
            logger.setLevel(logging.INFO)
    return attached


# ------------------------- Gỡ handler theo vòng đời --------------------------
def detach_logging(attached: list[tuple[logging.Logger, int, BufferHandler]]) -> None:
    """Gỡ đúng handler đã cài và khôi phục level, không đóng handler terminal."""
    for logger, level, handler in attached:
        logger.removeHandler(handler)
        logger.setLevel(level)
        handler.close()
