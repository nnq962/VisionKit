"""Các thông số inference ảnh được kiểm tra trước khi nạp model."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


# ---------------------------- Thông số inference -----------------------------
class PredictOptions(BaseModel):
    """Giới hạn cấu hình ảnh; device auto chọn phần cứng thực tế trong worker."""

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
