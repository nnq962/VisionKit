"""Hợp đồng nội bộ cho một lượt inference trên ảnh gốc."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.options import PredictOptions


# ---------------------------- Yêu cầu inference ------------------------------
class PredictRequest(BaseModel):
    """Nhận hai file trong storage chung và checksum, không nhận URL mạng tuỳ ý."""

    model_config = ConfigDict(extra="forbid")
    model_location: str = Field(min_length=1, max_length=255)
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_location: str = Field(min_length=1, max_length=255)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    family: Literal["yolo", "yoloe"] = "yolo"
    task: Literal["detect", "pose", "classify", "segment", "obb"] = "detect"
    options: PredictOptions = Field(default_factory=PredictOptions)
