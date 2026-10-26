"""Request kiểm tra RTSP tạm, không tạo nguồn trong thư viện."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from app.core.rtsp import validate_rtsp_url


# ------------------------- Yêu cầu xem thử camera ----------------------------
class TemporaryPreviewCreate(BaseModel):
    """Nhận định danh browser và URL bí mật cho phiên RAM có lease giới hạn."""

    model_config = ConfigDict(extra="forbid")
    preview_id: UUID
    url: SecretStr

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: SecretStr) -> SecretStr:
        """Kiểm URL RTSP/RTSPS, thông báo lỗi không phản chiếu credentials."""
        return SecretStr(validate_rtsp_url(value.get_secret_value()))
