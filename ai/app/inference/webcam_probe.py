"""Kiểm webcam local trong child process, không nạp YOLO hoặc giữ camera sau kiểm tra."""

import contextlib
import json
import sys


# ----------------------------- Kiểm camera local -----------------------------
def main() -> None:
    """Mở một frame, trả metadata/preview rồi release; service cha giới hạn thời gian."""
    output = sys.stdout
    try:
        from app.adapters.ultralytics.stream import webcam_preview
        from app.contracts.prediction import WebcamCheckRequest
        from app.media_sources import create_media_source

        request = WebcamCheckRequest.model_validate_json(sys.stdin.read())
        with contextlib.redirect_stdout(sys.stderr):
            with create_media_source(request.device_index, warmup_seconds=1) as reader:
                frame, meta = reader.read()
                result = {
                    "device_index": request.device_index,
                    "width": meta.resolution[0],
                    "height": meta.resolution[1],
                    "preview_jpeg": webcam_preview(frame),
                }
        print(json.dumps(result), file=output)
    except Exception:
        print(
            json.dumps(
                {
                    "error": "Không mở được webcam trên máy AI. Kiểm tra ID, cấp quyền camera cho Python/Terminal và đóng ứng dụng đang dùng camera."
                }
            ),
            file=output,
        )


if __name__ == "__main__":
    main()
