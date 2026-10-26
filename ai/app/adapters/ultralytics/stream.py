"""Chạy RTSP bằng reader latest-frame; không lưu/stream ảnh nhị phân về backend."""

import time
from collections.abc import Callable
from pathlib import Path

from app.adapters.ultralytics.results import serialize_result
from app.adapters.ultralytics.yolo import load_model
from app.contracts.prediction import StreamPredictRequest
from app.media_sources import StreamBatchReader, create_media_source


# ----------------------------- Suy luận RTSP ---------------------------------
def predict_stream(
    model_path: Path, request: StreamPredictRequest, publish: Callable[[dict], None]
) -> None:
    """Nạp model một lần, đọc latest-frame và gửi NDJSON metadata/kết quả theo thời hạn.

    Giới hạn nhịp AI theo max_fps; frame cũ bị thay trong slot hữu hạn. vid_stride theo
    index nguồn. Hết hạn trả completed; EOF/mất camera là lỗi, không completed.
    """
    model, device = load_model(model_path, request)
    reader = create_media_source(
        request.stream_url.get_secret_value(),
        reconnect_delay=1,
        max_reconnect_attempts=5,
        read_timeout_ms=3000,
        open_timeout_ms=5000,
    )
    # Chờ lâu hơn read timeout để capture thread tự release trước terminal event.
    with StreamBatchReader([reader], join_timeout=6, wait_timeout=15) as sources:
        started = time.perf_counter()
        started_wall = time.time()
        processed = 0
        latest = None
        progress = None
        next_index = 0
        next_due = started
        while time.perf_counter() - started < request.duration_seconds:
            wait = next_due - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            if time.perf_counter() - started >= request.duration_seconds:
                break
            frames, metas = next(sources)
            meta = metas[0]
            if meta.frame_index < next_index:
                continue
            next_index = meta.frame_index + request.options.vid_stride
            options = request.options
            next_due = time.perf_counter() + 1 / options.max_fps
            result = model.predict(
                source=frames[0],
                conf=options.conf,
                iou=options.iou,
                imgsz=list(options.imgsz),
                device=device,
                classes=options.classes,
                max_det=options.max_det,
                agnostic_nms=options.agnostic_nms,
                save=False,
                verbose=False,
            )[0]
            elapsed = time.perf_counter() - started
            latest = serialize_result(result, device, elapsed)
            latest.update(
                frameId=meta.frame_index,
                timestampMs=round(max(0, meta.timestamp - started_wall) * 1000, 2),
            )
            processed += 1
            progress = {
                "frames_processed": processed,
                "frame_index": meta.frame_index,
                "total_frames": None,
                "timestamp_ms": latest["timestampMs"],
                "source_fps": meta.fps,
                "processing_fps": round(processed / max(0.001, elapsed), 2),
                "percent": None,
                "is_live": True,
                "elapsed_seconds": round(elapsed, 2),
            }
            publish({"type": "frame", "result": latest, "progress": progress})
        if latest is None:
            raise ValueError("Không nhận được frame suy luận từ camera.")
    publish(
        {
            "type": "completed",
            "reason": "duration_limit",
            "result": latest,
            "progress": progress,
        }
    )
