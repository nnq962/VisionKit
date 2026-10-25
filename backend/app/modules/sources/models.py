"""Các kiểu dữ liệu source dùng chung giữa repository, service và API."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


# ------------------------------ Các loại source ------------------------------
class SourceKind(str, Enum):
    """Liệt kê các loại source được lưu; giá trị chuỗi đồng nhất với schema SQLite."""

    IMAGE = "image"
    VIDEO = "video"
    STREAM = "stream"
    YOUTUBE = "youtube"
    WEBCAM = "webcam"
    SCREEN = "screen"
    DIRECTORY = "directory"
    URL = "url"


# ------------------------------ Bản ghi source -------------------------------
@dataclass(frozen=True)
class Source:
    """Bản ghi source bất biến ở cấp thuộc tính, dùng giữa repository và service.

    Thuộc tính:
        id: UUID của source.
        name: Tên hiển thị.
        kind: Loại file, URL hoặc thiết bị.
        location: Vị trí nguồn, không chứa dữ liệu nhị phân.
        metadata: Thông tin linh hoạt như kích thước, thời lượng, định dạng.
        created_at: Thời điểm tạo có múi giờ UTC.
        updated_at: Thời điểm cập nhật gần nhất có múi giờ UTC.
    """

    id: str
    name: str
    kind: SourceKind
    location: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
