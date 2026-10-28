"""Cấu hình class/vùng và snapshot theo lượt chạy; không chứa URL nguồn."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .geometry import valid_polygon

CLASSES = (
    "person",
    "wheelchair",
    "hospital stretcher",
    "hospital bed",
    "medical trolley",
    "IV pole",
)
Coordinate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


# ------------------------- Chuẩn hoá danh sách class -------------------------
def validate_class_names(value: list[str]) -> list[str]:
    """Từ chối prompt trùng hoặc ký tự điều khiển trước khi lưu và gửi sang AI."""
    if len({item.casefold() for item in value}) != len(value):
        raise ValueError("Danh sách class không được trùng nhau.")
    if any(any(ord(char) < 32 or ord(char) == 127 for char in item) for item in value):
        raise ValueError("Class không được chứa ký tự điều khiển.")
    return value


ClassName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
ClassNames = Annotated[
    list[ClassName],
    Field(min_length=1, max_length=80),
    AfterValidator(validate_class_names),
]


# ---------------------------- Vùng đếm chuẩn hoá -----------------------------
class CountingZone(BaseModel):
    """Giữ ID, tên, màu, đỉnh polygon 0–1 và tập class cần đếm trong vùng."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: UUID
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
    ]
    color: str = Field(default="#22d3ee", pattern=r"^#[0-9a-fA-F]{6}$")
    points: list[tuple[Coordinate, Coordinate]] = Field(min_length=3, max_length=32)
    classes: ClassNames = Field(default_factory=lambda: list(CLASSES))

    @field_validator("points")
    @classmethod
    def simple_polygon(
        cls, value: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        """Từ chối vùng tự cắt, trùng đỉnh hoặc không có diện tích trước khi lưu/chạy."""
        if not valid_polygon(value):
            raise ValueError(
                "Vùng không được tự cắt, trùng đỉnh hoặc có diện tích bằng không."
            )
        return value


# ----------------------------- Bộ cấu hình vùng ------------------------------
class CountingConfig(BaseModel):
    """Lưu vùng chuẩn hoá và kích thước ảnh lúc vẽ để phát hiện đổi tỷ lệ khung hình."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    classes: ClassNames = Field(default_factory=lambda: list(CLASSES))
    reference_width: int = Field(ge=1, le=32768)
    reference_height: int = Field(ge=1, le=32768)
    zones: list[CountingZone] = Field(default_factory=list, max_length=20)

    @field_validator("zones")
    @classmethod
    def unique_ids(cls, value: list[CountingZone]) -> list[CountingZone]:
        """Từ chối ID vùng trùng nhau để kết quả và thao tác sửa không nhập nhằng."""
        if len({zone.id for zone in value}) != len(value):
            raise ValueError("ID vùng không được trùng.")
        return value

    @model_validator(mode="after")
    def known_zone_classes(self) -> "CountingConfig":
        """Đảm bảo mỗi class được đếm thuộc danh sách prompt của cấu hình lượt chạy."""
        known = set(self.classes)
        if any(not set(zone.classes).issubset(known) for zone in self.zones):
            raise ValueError("Class trong vùng phải thuộc danh sách class YOLOE.")
        return self
