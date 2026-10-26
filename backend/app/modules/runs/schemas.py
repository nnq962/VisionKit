"""Hợp đồng cấu hình và trạng thái lượt chạy ảnh."""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
    max_det: int = Field(default=300, ge=1, le=3000)
    agnostic_nms: bool = False
    vid_stride: int = Field(default=1, ge=1, le=120)


# ------------------------------- Bản ghi chạy --------------------------------
class RunRecord(BaseModel):
    """Lưu trạng thái, ảnh đầu vào riêng và JSON kết quả; không chứa model hoặc tensor."""

    id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    source_kind: Literal["image", "screen", "video", "stream"] = "image"
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
