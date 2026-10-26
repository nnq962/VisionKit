"""Hợp đồng request/response của API quản lý nguồn ảnh."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.core.rtsp import validate_rtsp_url

from .models import SourceKind


# ------------------------------ Response source ------------------------------
class SourceResponse(BaseModel):
    """Thông tin source lưu bền vững; content_url dùng để tải ảnh preview."""

    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    kind: SourceKind
    location: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    content_url: str | None = None
    preview_url: str | None = None


# -------------------------- Trang danh sách source ---------------------------
class SourcePage(BaseModel):
    """Danh sách source theo trang kèm tổng số bản ghi khớp bộ lọc."""

    items: list[SourceResponse]
    total: int
    limit: int
    offset: int


# -------------------------- Request đổi tên source ---------------------------
class SourceRename(BaseModel):
    """Chỉ cho phép đổi tên source; từ chối trường lạ và tên rỗng."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> Any:
        """Bỏ khoảng trắng hai đầu trước khi kiểm tra giới hạn tên.

        Tham số:
            value: Giá trị tên nhận từ JSON, có thể chưa đúng kiểu.
        Trả về:
            Chuỗi đã chuẩn hoá hoặc giá trị gốc để Pydantic báo lỗi kiểu.
        """
        return value.strip() if isinstance(value, str) else value


# --------------------------- Cấu hình source RTSP ----------------------------
class RtspSourceCreate(SourceRename):
    """Lưu tên và URL bí mật; không kết nối camera lúc tạo source."""

    url: SecretStr

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: SecretStr) -> SecretStr:
        """Kiểm URL RTSP/RTSPS mà không ghi credentials vào lỗi validation."""
        return SecretStr(validate_rtsp_url(value.get_secret_value()))
