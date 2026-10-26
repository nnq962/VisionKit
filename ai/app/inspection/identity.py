"""Nhận diện dòng YOLO từ định danh cấu hình/metadata nhúng, không dùng tên file upload."""

import re

PATTERN = re.compile(
    r"(?<![a-z0-9])(?P<family>yoloe|yolo)[-_ ]?v?(?P<generation>26|12|11|10|9|8|5)"
    r"(?P<scale>[nsmlx])?(?=$|[^a-z0-9])",
    re.IGNORECASE,
)


# --------------------------- Đọc định danh nhúng -----------------------------
def model_identity(value: object, family: str | None) -> tuple[str | None, str | None]:
    """Trả dòng/scale khi chuỗi nhúng có một định danh YOLO duy nhất và khớp family.

    Tham số:
        value: yaml_file bên trong checkpoint hoặc mô tả/định danh ONNX nhúng.
        family: Họ đã xác định độc lập từ checkpoint hoặc metadata ONNX.
    Trả về:
        Cặp (dòng, scale); None khi thiếu, mơ hồ hoặc family không khớp.
        Đây là thông tin do file khai báo, không xác minh kiến trúc qua inference.
    """
    if not isinstance(value, str) or len(value) > 4096 or not family:
        return None, None
    matches = list(PATTERN.finditer(value))
    identities = {
        (match["family"].lower(), match["generation"], (match["scale"] or "").lower())
        for match in matches
    }
    if len(identities) != 1:
        return None, None
    declared_family, generation, scale = identities.pop()
    if declared_family != family:
        return None, None
    series = (
        f"YOLOE-{generation}"
        if family == "yoloe"
        else f"YOLOv{generation}"
        if int(generation) <= 10
        else f"YOLO{generation}"
    )
    return series, scale or None
