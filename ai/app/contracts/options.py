"""Các thông số inference ảnh được kiểm tra trước khi nạp model."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------- Thông số inference -----------------------------
class PredictOptions(BaseModel):
    """Giới hạn cấu hình ảnh; device auto chọn phần cứng thực tế trong worker."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    conf: float = Field(default=0.25, ge=0, le=1)
    iou: float = Field(default=0.7, ge=0, le=1)
    imgsz: tuple[int, int] = (640, 640)
    device: Literal["auto", "cpu", "cuda:0", "mps"] = "auto"
    classes: list[int] | None = Field(default=None, max_length=10000)
    max_det: int = Field(default=300, ge=1, le=3000)
    agnostic_nms: bool = False
    vid_stride: int = Field(default=1, ge=1, le=120)
    max_fps: float = Field(default=5, ge=1, le=60)
