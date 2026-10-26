"""Chuyển kết quả Ultralytics sang JSON canvas ở toạ độ ảnh gốc."""

import math
from typing import Any


# ---------------------------- Chuẩn hoá kết quả ------------------------------
def serialize_result(result: Any, device: str, elapsed: float) -> dict:
    """Đọc tensor đã inference, trả bbox/keypoint/top5/polygon; không vẽ hoặc lưu ảnh.

    Toạ độ xyxy/xy đều theo orig_shape đã hoàn nguyên preprocessing của
    Ultralytics. Polygon segmentation/OBB giữ trong JSON để mở rộng renderer.
    """
    detections = []
    boxes = result.boxes
    if boxes is not None:
        for index, box in enumerate(boxes):
            class_id = int(box.cls.item())
            item = {
                "id": index,
                "classId": class_id,
                "label": result.names.get(class_id, str(class_id)),
                "confidence": float(box.conf.item()),
                "bbox": box.xyxy[0].cpu().tolist(),
            }
            if result.keypoints is not None:
                xy = result.keypoints.xy[index].cpu().tolist()
                scores = result.keypoints.conf
                item["keypoints"] = [
                    {
                        "x": point[0],
                        "y": point[1],
                        "confidence": float(scores[index][keypoint].item())
                        if scores is not None
                        else 1.0,
                    }
                    for keypoint, point in enumerate(xy)
                ]
            if result.masks is not None:
                item["polygon"] = result.masks.xy[index].tolist()
            detections.append(item)
    if result.obb is not None:
        for index, box in enumerate(result.obb):
            class_id = int(box.cls.item())
            detections.append(
                {
                    "id": index,
                    "classId": class_id,
                    "label": result.names.get(class_id, str(class_id)),
                    "confidence": float(box.conf.item()),
                    "bbox": box.xyxy[0].cpu().tolist(),
                    "polygon": box.xyxyxyxy[0].cpu().tolist(),
                }
            )
    classifications = []
    if result.probs is not None:
        classifications = [
            {
                "classId": int(index),
                "label": result.names[index],
                "confidence": float(result.probs.data[index].item()),
            }
            for index in result.probs.top5
        ]
    speed = {
        key: float(value)
        for key, value in result.speed.items()
        if value is not None and math.isfinite(float(value))
    }
    return {
        "frameId": 0,
        "sourceSize": {"width": result.orig_shape[1], "height": result.orig_shape[0]},
        "coordinates": "pixels",
        "detections": detections,
        "classifications": classifications,
        "device": device,
        "elapsedMs": round(elapsed * 1000, 2),
        "speed": speed,
    }
