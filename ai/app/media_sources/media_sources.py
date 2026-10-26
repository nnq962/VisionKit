"""Interface batch thống nhất, dùng context manager để thu hồi reader."""

from types import TracebackType
from typing import Any

from .batch import Batch
from .factory import create_media_source, is_sequence


# --------------------------- Đọc và quản lý source ---------------------------
class MediaSources:
    """Nguồn đơn cũng trả list frames/metas; mỗi meta mang source_index ổn định."""

    def __init__(self, sources: Any, **kwargs: Any) -> None:
        """Tạo batch lazy; chưa chiếm file/camera/kết nối mạng."""
        self._reader = create_media_source(
            sources if is_sequence(sources) else [sources], **kwargs
        )

    def __iter__(self) -> "MediaSources":
        """Trả iterator batch."""
        return self

    def __next__(self) -> Batch:
        """Trả các frame mới; không lưu lịch sử frame đã trả."""
        return next(self._reader)

    def __enter__(self) -> "MediaSources":
        """Mở batch tường minh và nhận quyền sở hữu tài nguyên."""
        self._reader.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Đóng toàn bộ nguồn kể cả vòng inference lỗi."""
        self.close()

    def close(self) -> None:
        """Thu hồi nguồn; báo lỗi nếu thread đọc vẫn chưa kết thúc."""
        self._reader.close()

    def release(self) -> None:
        """Alias close tương thích API của module gốc."""
        self.close()
