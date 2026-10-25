"""Hợp đồng danh mục, model đã lưu và tiến độ tải model."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


# --------------------------- Thông tin file model ----------------------------
class ModelArtifact(BaseModel):
    """Metadata chung của weights tải từ catalog hoặc upload, không xác nhận chạy được.

    size không bắt buộc với model riêng. name là tên hiển thị tuỳ chọn; filename
    giữ tên file gốc. Các trường nguồn tải chỉ xuất hiện khi có thông tin tương ứng.
    """

    provider: str = "ultralytics"
    format: Literal["pt", "onnx"] = "pt"
    id: str
    familyId: str
    familyName: str
    filename: str
    task: Literal["detect", "segment", "pose", "classify", "obb"] | None = None
    size: Literal["n", "s", "m", "l", "x"] | None = None
    name: str | None = None
    origin: Literal["catalog", "upload"] = "catalog"
    url: str | None = None
    expected_bytes: int | None = None
    sha256: str | None = None
    release: str | None = None


# ---------------------------- Model trong catalog ----------------------------
class CatalogVariant(ModelArtifact):
    """File catalog đã ghim release, dung lượng và SHA-256 từ GitHub chính thức."""

    size: Literal["n", "s", "m", "l", "x"]
    task: Literal["detect", "segment", "pose", "classify", "obb"]
    url: str
    expected_bytes: int
    sha256: str
    release: str


# ----------------------------- Yêu cầu tải model -----------------------------
class DownloadRequest(BaseModel):
    """Chỉ nhận catalog_id trong danh mục; không nhận URL hoặc đường dẫn tuỳ ý."""

    model_config = ConfigDict(extra="forbid")
    catalog_id: str = Field(min_length=1, max_length=120)


# ---------------------------- Metadata do AI đọc -----------------------------
class InspectionMetadata(BaseModel):
    """Hợp đồng metadata HTTP từ module AI, chỉ chứa các trường đã đọc được."""

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


# ---------------------------- Trạng thái metadata ----------------------------
class ModelInspection(BaseModel):
    """Lưu trạng thái bền vững của việc đọc metadata, không xác nhận inference thành công."""

    status: Literal[
        "uninspected",
        "queued",
        "processing",
        "ready",
        "needs_input",
        "failed",
        "unavailable",
        "manual",
    ] = "uninspected"
    metadata: InspectionMetadata | None = None
    message: str | None = None
    updated_at: str | None = None


# ----------------------------- Khai báo thủ công -----------------------------
class ModelConfiguration(BaseModel):
    """Nhận họ model và tác vụ khi metadata thiếu hoặc AI chưa kết nối."""

    model_config = ConfigDict(extra="forbid")
    family: Literal["yolo", "yoloe"]
    task: Literal["detect", "segment", "pose", "classify", "obb"]


# ------------------------------- Model đã lưu --------------------------------
class StoredModel(BaseModel):
    """Bản ghi model đã lưu hoàn chỉnh, với vị trí tương đối và checksum xác minh."""

    id: str
    variant: ModelArtifact
    location: str
    size_bytes: int
    sha256: str
    saved_at: str
    inspection: ModelInspection = Field(default_factory=ModelInspection)


# ------------------------------ Trạng thái tải -------------------------------
class DownloadJob(BaseModel):
    """Tiến độ bền vững; chỉ completed sau khi file và bản ghi model đã được lưu."""

    id: str
    variant: CatalogVariant
    status: Literal["queued", "downloading", "completed", "failed", "cancelled"]
    downloaded_bytes: int
    total_bytes: int
    error: str | None = None
    created_at: str
    updated_at: str

    @computed_field
    @property
    def progress(self) -> int:
        """Trả phần trăm byte, tối đa 99 trước khi hoàn tất transaction lưu model."""
        if self.status == "completed":
            return 100
        return min(99, self.downloaded_bytes * 100 // max(1, self.total_bytes))
