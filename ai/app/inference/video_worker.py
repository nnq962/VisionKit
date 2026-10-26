"""Worker video: stdin một request, stdout NDJSON gồm frame và sự kiện terminal."""

import contextlib
import hashlib
import json
import logging
import os
import sys
import traceback
from pathlib import Path


# ------------------------------- Worker video --------------------------------
def main() -> None:
    """Xác minh checksum, chạy video và flush mỗi sự kiện; lỗi luôn trả event error."""
    os.environ.update(
        YOLO_AUTOINSTALL="false",
        YOLO_OFFLINE="true",
        ULTRALYTICS_SAFE_LOAD="true",
        OMP_NUM_THREADS="2",
        OPENCV_FFMPEG_CAPTURE_OPTIONS="protocol_whitelist;file,pipe",
    )
    from app.adapters.ultralytics.video import predict_video
    from app.contracts.prediction import PredictRequest

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    output = sys.stdout

    def publish(event: dict) -> None:
        """Ghi một dòng JSON vào pipe cho API cha, không lẫn log Ultralytics."""
        print(json.dumps(event, allow_nan=False), file=output, flush=True)

    try:
        request = PredictRequest.model_validate_json(sys.stdin.read())
        model, source = Path(sys.argv[1]), Path(sys.argv[2])
        for path, expected in [
            (model, request.model_sha256),
            (source, request.source_sha256),
        ]:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("File đã thay đổi checksum. Hãy tải lại.")
        with contextlib.redirect_stdout(sys.stderr):
            predict_video(model, source, request, publish)
    except ValueError as error:
        publish(
            {
                "type": "error",
                "error": str(error)[:250],
                "traceback": traceback.format_exc()[-8192:],
            }
        )
    except Exception:
        traceback.print_exc(file=sys.stderr)
        publish(
            {
                "type": "error",
                "error": "Không xử lý được video bằng model đã chọn.",
                "traceback": traceback.format_exc()[-8192:],
            }
        )


if __name__ == "__main__":
    main()
