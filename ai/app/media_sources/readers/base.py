"""Reader đơn nguồn đồng bộ; chỉ thread sở hữu được phép gọi close/read."""

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Any

import numpy as np

from ..models import SourceMeta, SourceType


# --------------------------- Đọc và quản lý source ---------------------------
class BaseReader(ABC):
    """Vòng đời lazy open/read/close; dùng context manager để luôn giải phóng."""

    source_type: SourceType
    is_stream = False

    def __init__(self, source: Any) -> None:
        """Lưu nguồn; không mở file, camera hoặc mạng lúc khởi tạo."""
        self._source = source
        self._opened = False
        self._frame_index = 0

    @property
    def source(self) -> Any:
        """Trả nguồn gốc để factory/batch quản lý danh tính."""
        return self._source

    @property
    def opened(self) -> bool:
        """Reader đã mở và chưa được đóng."""
        return self._opened

    @abstractmethod
    def open(self) -> "BaseReader":
        """Mở idempotent; khi lỗi phải tự thu hồi tài nguyên đã tạo."""

    @abstractmethod
    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Trả frame/metadata hoặc None khi hết nguồn; lỗi giải mã phải raise."""

    @abstractmethod
    def close(self) -> None:
        """Giải phóng idempotent; không chạy đồng thời với read."""

    def ensure_open(self) -> None:
        """Mở lazy nếu chưa mở."""
        if not self._opened:
            self.open()

    def request_stop(self) -> None:
        """Đánh thức reconnect; không release capture đang được thread khác đọc."""

    def __iter__(self) -> "BaseReader":
        """Trả iterator đơn nguồn."""
        return self

    def __next__(self) -> tuple[np.ndarray, SourceMeta]:
        """Đọc tiếp, báo StopIteration khi hết nguồn."""
        result = self.read()
        if result is None:
            raise StopIteration
        return result

    def __enter__(self) -> "BaseReader":
        """Mở nguồn khi vào context."""
        self.ensure_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Luôn đóng khi rời context, kể cả consumer lỗi."""
        self.close()
