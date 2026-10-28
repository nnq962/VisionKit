"""Đếm hiện diện từ JSON detection; không chạy model hoặc giải mã video."""

import math

from .geometry import contains
from .schemas import CountingConfig


# -------------------------- Đếm vật thể trong vùng ---------------------------
def count_frame(result: dict, config: CountingConfig) -> dict:
    """Đếm điểm giữa đáy bbox theo mỗi vùng độc lập, không cộng dồn qua frame.

    Tham số: JSON kết quả AI theo pixel gốc và snapshot cấu hình của run.
    Trả về: kết quả valid/regions, frame/timestamp và lý do khi tỷ lệ ảnh đã đổi.
    Detection lỗi bị bỏ qua; không sửa result hoặc config và không ghi dữ liệu.
    """
    size = result.get("sourceSize", {})
    width, height = size.get("width", 0), size.get("height", 0)
    base = {
        "frame_id": result.get("frameId"),
        "timestamp_ms": result.get("timestampMs"),
        "anchor": "bottom_center",
    }
    if (
        not all(
            isinstance(v, (int, float)) and math.isfinite(v) and v > 0
            for v in (width, height)
        )
        or abs(
            (width / height) / (config.reference_width / config.reference_height) - 1
        )
        > 0.01
    ):
        return {
            **base,
            "valid": False,
            "reason": "Tỷ lệ khung hình đã đổi. Vẽ lại vùng trước khi chạy.",
            "regions": [],
        }
    objects = []
    for detection in result.get("detections", []):
        box = detection.get("bbox")
        label = detection.get("label")
        if (
            label not in config.classes
            or not isinstance(box, (list, tuple))
            or len(box) != 4
        ):
            continue
        if (
            not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
            or box[2] <= box[0]
            or box[3] <= box[1]
        ):
            continue
        x = min(1, max(0, (box[0] + box[2]) / (2 * width)))
        y = min(1, max(0, box[3] / height))
        objects.append((label, (x, y)))
    regions = []
    for zone in config.zones:
        counts = {label: 0 for label in zone.classes}
        for label, point in objects:
            if label in counts and contains(zone.points, point):
                counts[label] += 1
        regions.append(
            {
                "id": str(zone.id),
                "name": zone.name,
                "color": zone.color,
                "counts": counts,
                "total": sum(counts.values()),
            }
        )
    return {**base, "valid": True, "reason": None, "regions": regions}
