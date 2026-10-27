"""Worker RTSP riêng: nhận URL qua stdin và chỉ xuất NDJSON kết quả."""

import contextlib
import hashlib
import json
import logging
import os
import sys
from pathlib import Path


# ---------------------------- Worker nguồn RTSP ------------------------------
def main() -> None:
    """Xác minh model local, chỉ mở RTSP qua TCP/TLS và không lộ URL trong lỗi/native log.

    Capture native có thể ghi nguyên URL lên fd2; chuyển fd2 sang null, giữ logger
    Python qua bản sao stderr để collector vẫn nhận log đã kiểm soát.
    """
    os.environ.update(
        YOLO_AUTOINSTALL="false",
        YOLO_OFFLINE="true",
        ULTRALYTICS_SAFE_LOAD="true",
        OMP_NUM_THREADS="2",
        OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp|protocol_whitelist;rtsp,rtsps,tcp,tls,crypto",
    )
    output = sys.stdout
    safe_stderr = os.fdopen(os.dup(2), "w", buffering=1)
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 2)
    logging.basicConfig(level=logging.INFO, stream=safe_stderr, force=True)
    logger = logging.getLogger(__name__)

    def publish(event: dict) -> None:
        """Ghi một event đã chuẩn hóa vào stdout pipe; không ghi URL hoặc traceback."""
        print(json.dumps(event, allow_nan=False), file=output, flush=True)

    try:
        from app.adapters.ultralytics.stream import predict_stream
        from app.contracts.prediction import StreamPredictRequest, WebcamPredictRequest

        payload = json.loads(sys.stdin.read())
        contract = (
            WebcamPredictRequest if "device_index" in payload else StreamPredictRequest
        )
        request = contract.model_validate(payload)
        model = Path(sys.argv[1])
        digest = hashlib.sha256()
        with model.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != request.model_sha256:
            raise ValueError("Checksum model đã thay đổi.")
        with contextlib.redirect_stdout(safe_stderr):
            predict_stream(model, request, publish)
    except Exception as error:
        logger.error("Worker RTSP thất bại (%s).", type(error).__name__)
        publish(
            {
                "type": "error",
                "error": "Không đọc được camera. Kiểm tra ID, quyền camera của Python và ứng dụng đang dùng camera.",
            }
        )
    finally:
        safe_stderr.flush()


if __name__ == "__main__":
    main()
