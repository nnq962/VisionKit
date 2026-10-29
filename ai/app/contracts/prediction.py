"""Hợp đồng nội bộ cho một lượt inference trên ảnh gốc."""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

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

    @model_validator(mode="after")
    def valid_prompt_mode(self) -> "ModelPredictRequest":
        """Giới hạn text prompt cho YOLOE detect/segment, tách khỏi bộ lọc class."""
        if self.options.text_prompts is not None:
            if self.family != "yoloe" or self.task not in {"detect", "segment"}:
                raise ValueError("Text prompt chỉ hỗ trợ YOLOE detect/segment.")
            if self.options.classes is not None:
                raise ValueError("Không kết hợp text prompt với bộ lọc class ID.")
        return self


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


# ----------------------- Yêu cầu webcam trên máy AI ---------------------------
class WebcamCheckRequest(BaseModel):
    """Chỉ nhận index thiết bị local, không nhận URL/path từ trình duyệt."""

    model_config = ConfigDict(extra="forbid")
    device_index: int = Field(default=0, ge=0, le=15, strict=True)


# ------------------------- Suy luận webcam trực tiếp --------------------------
class WebcamPredictRequest(ModelPredictRequest):
    """YOLO đọc camera local theo index; preview giới hạn theo nhịp suy luận."""

    device_index: int = Field(default=0, ge=0, le=15, strict=True)
    duration_seconds: int = Field(default=3600, ge=1, le=14400, strict=True)

    def worker_payload(self) -> bytes:
        """Xuất JSON cho worker local, không có đường dẫn camera tuỳ ý."""
        return self.model_dump_json().encode()
