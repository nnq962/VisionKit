"""Inference video local theo từng frame, nạp model một lần và xuất kết quả mới nhất."""

import time
from collections.abc import Callable
from pathlib import Path

from app.adapters.ultralytics.results import serialize_result
from app.adapters.ultralytics.yolo import load_model
from app.contracts.prediction import PredictRequest


# ------------------------------- Chạy video file -----------------------------
def predict_video(
    model_path: Path,
    video_path: Path,
    request: PredictRequest,
    publish: Callable[[dict], None],
) -> None:
    """Đọc video bằng OpenCV, lấy mỗi N frame và phát sự kiện JSON gốc; không lưu timeline.

    Model được nạp một lần. Pacing không cho AI chạy nhanh hơn thời gian video;
    máy chậm vẫn xử lý theo stride và có thể trễ preview. Luôn giải phóng capture.
    """
    import cv2

    model, device = load_model(model_path, request)
    capture = cv2.VideoCapture(str(video_path), cv2.CAP_FFMPEG)
    capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
    try:
        if not capture.isOpened():
            raise ValueError("Không mở được video.")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not 0 < fps < 1000:
            raise ValueError("Không xác định được frame rate video.")
        total = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        started = time.perf_counter()
        processed = 0
        index = -1
        latest = None
        progress = None
        while capture.grab():
            index += 1
            if index % request.options.vid_stride:
                continue
            ok, frame = capture.retrieve()
            if not ok:
                raise ValueError("Không giải mã được frame video.")
            frame_ms = index / fps * 1000
            delay = frame_ms / 1000 - (time.perf_counter() - started)
            if delay > 0:
                time.sleep(delay)
            result = model.predict(
                source=frame,
                conf=request.options.conf,
                iou=request.options.iou,
                imgsz=list(request.options.imgsz),
                device=device,
                classes=request.options.classes,
                max_det=request.options.max_det,
                agnostic_nms=request.options.agnostic_nms,
                save=False,
                verbose=False,
            )[0]
            latest = serialize_result(result, device, time.perf_counter() - started)
            latest.update(frameId=index, timestampMs=round(frame_ms, 2))
            processed += 1
            progress = {
                "frames_processed": processed,
                "frame_index": index,
                "total_frames": total or None,
                "timestamp_ms": round(frame_ms, 2),
                "source_fps": fps,
                "processing_fps": round(
                    processed / max(0.001, time.perf_counter() - started), 2
                ),
                "percent": min(99.9, round((index + 1) / total * 100, 1))
                if total
                else None,
            }
            publish({"type": "frame", "result": latest, "progress": progress})
        if latest is None:
            raise ValueError("Video không có frame giải mã được.")
        progress = {**progress, "percent": 100}
        publish({"type": "completed", "result": latest, "progress": progress})
    finally:
        capture.release()
