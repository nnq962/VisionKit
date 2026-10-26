"""Hợp đồng nội bộ cho một lượt inference trên ảnh gốc."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.contracts.options import PredictOptions
from app.core.rtsp import validate_rtsp_url


# ---------------------------- Yêu cầu inference ------------------------------
class ModelPredictRequest(BaseModel):
    """Thông số model chung; đường dẫn và checksum luôn được xác minh tại worker."""

    model_config = ConfigDict(extra="forbid")
    model_location: str = Field(min_length=1, max_length=255)
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    family: Literal["yolo", "yoloe"] = "yolo"
    task: Literal["detect", "pose", "classify", "segment", "obb"] = "detect"
    options: PredictOptions = Field(default_factory=PredictOptions)


# -------------------------- Yêu cầu xử lý file local --------------------------
class PredictRequest(ModelPredictRequest):
    """Nhận hai file trong storage chung và checksum, không mở URL nguồn mạng."""

    source_location: str = Field(min_length=1, max_length=255)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


# --------------------------- Yêu cầu xử lý RTSP ------------------------------
class StreamPredictRequest(ModelPredictRequest):
    """Hợp đồng nội bộ riêng cho RTSP; không chấp nhận file hoặc protocol khác."""

    stream_url: SecretStr
    duration_seconds: int = Field(default=3600, ge=1, le=14400, strict=True)

    @field_validator("stream_url")
    @classmethod
    def valid_url(cls, value: SecretStr) -> SecretStr:
        """Kiểm URL mà không đưa credentials vào repr hoặc thông báo lỗi."""
        return SecretStr(validate_rtsp_url(value.get_secret_value()))

    def worker_payload(self) -> bytes:
        """Chỉ bỏ mask để truyền qua stdin worker; không gọi hàm này cho response/log."""
        import json

        payload = self.model_dump(mode="json")
        payload["stream_url"] = self.stream_url.get_secret_value()
        return json.dumps(payload, allow_nan=False).encode()
