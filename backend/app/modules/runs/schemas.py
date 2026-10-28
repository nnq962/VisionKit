"""Hợp đồng cấu hình và trạng thái lượt chạy ảnh."""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.modules.counting.schemas import CountingConfig


# ------------------------------ Hạn dùng lượt chạy ---------------------------
def run_expiry() -> str:
    """Trả hạn 24 giờ cho bản ghi cũ chưa có expiry; không sửa source hoặc file thư viện."""
    return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()


# ----------------------------- Cấu hình lượt chạy ----------------------------
class RunOptions(BaseModel):
    """Nhận thông số số học đã chuẩn hoá, không cho truyền tham số Ultralytics tuỳ ý."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    conf: float = Field(default=0.25, ge=0, le=1)
    iou: float = Field(default=0.7, ge=0, le=1)
    imgsz: tuple[int, int] = (640, 640)
    device: Literal["auto", "cpu", "cuda:0", "mps"] = "auto"
    classes: list[int] | None = Field(default=None, max_length=10000)
    text_prompts: (
        list[
            Annotated[
                str,
                StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
            ]
        ]
        | None
    ) = Field(default=None, min_length=1, max_length=80)
    max_det: int = Field(default=300, ge=1, le=3000)
    agnostic_nms: bool = False
    vid_stride: int = Field(default=1, ge=1, le=120)
    max_fps: float = Field(default=5, ge=1, le=60)

    @field_validator("text_prompts")
    @classmethod
    def unique_prompts(cls, value: list[str] | None) -> list[str] | None:
        """Từ chối prompt trùng hoặc ký tự điều khiển để giữ class ID ổn định."""
        if value is not None:
            if len({item.casefold() for item in value}) != len(value):
                raise ValueError("Danh sách prompt không được trùng nhau.")
            if any(
                any(ord(char) < 32 or ord(char) == 127 for char in item)
                for item in value
            ):
                raise ValueError("Prompt không được chứa ký tự điều khiển.")
        return value


# ------------------------------- Bản ghi chạy --------------------------------
class RunRecord(BaseModel):
    """Lưu trạng thái, ảnh đầu vào riêng và JSON kết quả; không chứa model hoặc tensor."""

    id: str
    counting: CountingConfig | None = None
    counts: dict[str, Any] | None = None
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    source_kind: Literal["image", "screen", "video", "stream", "webcam"] = "image"
    progress: dict[str, Any] | None = None
    model_id: str
    source_location: str
    source_metadata: dict[str, Any]
    options: RunOptions
    result: dict[str, Any] | None = None
    error: str | None = None
    completion_reason: Literal["duration_limit"] | None = None
    expires_at: str = Field(default_factory=run_expiry)
    created_at: str
    updated_at: str


# --------------------------- Yêu cầu chạy camera -----------------------------
class StreamRunCreate(BaseModel):
    """Chạy RTSP từ source ID đã lưu; không cho truyền URL camera trực tiếp vào run."""

    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=255)
    source_id: UUID
    options: RunOptions = Field(default_factory=RunOptions)
    duration_seconds: int = Field(default=3600, ge=1, le=14400, strict=True)


# ---------------------------- Chạy AI từ relay -------------------------------
class LiveRunCreate(BaseModel):
    """Chọn đúng một camera thư viện hoặc preview tạm; không nhận URL từ browser."""

    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=255)
    source_id: UUID | None = None
    preview_id: UUID | None = None
    options: RunOptions = Field(default_factory=RunOptions)
    duration_seconds: int = Field(default=3600, ge=1, le=14400, strict=True)

    @model_validator(mode="after")
    def one_source(self) -> "LiveRunCreate":
        """Từ chối nguồn thiếu hoặc mơ hồ trước khi giữ relay/model."""
        if (self.source_id is None) == (self.preview_id is None):
            raise ValueError("Chọn đúng một camera hoặc preview.")
        return self


# -------------------------- Chạy video YouTube tạm ----------------------------
class YoutubeRunCreate(BaseModel):
    """Chọn video đã chuẩn bị để snapshot và tái sử dụng inference video local."""

    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=255)
    session_id: UUID
    options: RunOptions = Field(default_factory=RunOptions)


# ------------------------- Webcam local và lượt chạy --------------------------
class WebcamCheckRequest(BaseModel):
    """Chỉ kiểm index camera trên máy AI, không chấp nhận đường dẫn hoặc URL."""

    model_config = ConfigDict(extra="forbid")
    device_index: int = Field(default=0, ge=0, le=15, strict=True)


# ----------------------------- Chạy webcam local -----------------------------
class WebcamRunCreate(WebcamCheckRequest):
    """Nhận model và thông số live cho webcam local; mặc định camera 0."""

    model_id: str = Field(min_length=1, max_length=255)
    options: RunOptions = Field(default_factory=RunOptions)
    duration_seconds: int = Field(default=3600, ge=1, le=14400, strict=True)
