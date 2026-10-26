"""Worker inference ảnh độc lập, stdout chỉ trả JSON và không truy cập DB."""

import contextlib
import hashlib
import json
import os
import sys
from pathlib import Path


# ----------------------------- Chạy worker ảnh -------------------------------
def main() -> None:
    """Nhận request qua stdin, xác minh file/checksum rồi inference; trả lỗi có kiểm soát."""
    os.environ.update(
        YOLO_AUTOINSTALL="false",
        YOLO_OFFLINE="true",
        ULTRALYTICS_SAFE_LOAD="true",
        OMP_NUM_THREADS="2",
    )
    from app.adapters.ultralytics.yolo import predict_image
    from app.contracts.prediction import PredictRequest

    try:
        request = PredictRequest.model_validate_json(sys.stdin.read())
        model_path, source_path = Path(sys.argv[1]), Path(sys.argv[2])
        for path, expected in [
            (model_path, request.model_sha256),
            (source_path, request.source_sha256),
        ]:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise ValueError("File đã thay đổi checksum. Hãy tải lại.")
        with contextlib.redirect_stdout(sys.stderr):
            result = predict_image(model_path, source_path, request)
        output = {"result": result}
    except ValueError as error:
        output = {"error": str(error)[:250]}
    except Exception:
        output = {
            "error": "Không chạy được model. Kiểm tra định dạng và khả năng tương thích của model."
        }
    print(json.dumps(output, allow_nan=False))


if __name__ == "__main__":
    main()
