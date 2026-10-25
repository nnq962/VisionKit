"""Hợp đồng HTTP đọc metadata weights, tách khỏi việc chạy inference."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ----------------------------- Yêu cầu đọc model -----------------------------
class InspectRequest(BaseModel):
    """Nhận vị trí tương đối trong storage chung và SHA-256 mà backend đã lưu."""

    model_config = ConfigDict(extra="forbid")
    location: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


# ------------------------------ Metadata model -------------------------------
class ModelMetadata(BaseModel):
    """Thông tin thực đọc được; None biểu thị không có bằng chứng xác định trường đó."""

    format: Literal["pt", "onnx"]
    family: Literal["yolo", "yoloe"] | None = None
    task: Literal["detect", "segment", "pose", "classify", "obb"] | None = None
    names: dict[str, str] = Field(default_factory=dict)
    class_count: int | None = None
    imgsz: list[int] | None = None
    input_shape: list[int | str | None] | None = None
    stride: int | None = None
    model_type: str | None = None
    scale: str | None = None
    parameters: int | None = None
    producer: str | None = None
    version: str | None = None


# --------------------------- Kết quả đọc metadata ----------------------------
class InspectResult(BaseModel):
    """Phân biệt đọc đủ thông tin, thiếu metadata và file không đọc được."""

    status: Literal["ready", "needs_input", "failed"]
    metadata: ModelMetadata | None = None
    message: str | None = None
