"""Metadata độc lập với model; timestamp video tách biệt giờ hệ thống."""

from dataclasses import dataclass
from enum import Enum


# --------------------------- Đọc và quản lý source ---------------------------
class SourceType(str, Enum):
    """Các loại nguồn mà factory có thể lựa chọn."""

    IMAGE = "image"
    VIDEO = "video"
    WEBCAM = "webcam"
    RTSP = "rtsp"
    YOUTUBE = "youtube"


# --------------------------- Đọc và quản lý source ---------------------------
@dataclass(frozen=True)
class SourceMeta:
    """Mô tả frame; source_index giữ danh tính khi batch có nguồn hết trước.

    timestamp là Unix giây lúc đọc; timestamp_ms là vị trí trong video,
    không phải thời gian suy luận. Với live stream, timestamp_ms là None.
    """

    name: str
    source_type: SourceType
    frame_index: int
    resolution: tuple[int, int]
    fps: float | None = None
    total_frames: int | None = None
    is_stream: bool = False
    timestamp: float = 0.0
    timestamp_ms: float | None = None
    source_index: int = 0
