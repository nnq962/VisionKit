"""Entry point tiến trình đọc model; stdout chỉ chứa kết quả JSON cho API cha."""

import contextlib
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

from app.contracts.model import InspectResult


# --------------------------- Chạy worker kiểm tra ----------------------------
def main() -> None:
    """Đọc file từ argv, kiểm checksum và trả JSON; lỗi giải mã không làm chết API cha.

    Mỗi lượt chạy trong tiến trình riêng, chỉ dùng CPU, tắt tự tải/cài dependency.
    Không coi metadata ready là kết quả kiểm thử inference thành công.
    """
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["YOLO_OFFLINE"] = "true"
    os.environ["ULTRALYTICS_SAFE_LOAD"] = "true"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["OMP_NUM_THREADS"] = "1"
    path = Path(sys.argv[1])
    trace = None
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != sys.argv[2]:
            raise ValueError("Checksum file model không khớp.")
        with contextlib.redirect_stdout(sys.stderr):
            if path.suffix.lower() == ".pt":
                from app.inspection.pt import inspect_pt

                metadata = inspect_pt(path)
            else:
                from app.inspection.onnx import inspect_onnx

                metadata = inspect_onnx(path)
        complete = metadata.family is not None and metadata.task is not None
        result = InspectResult(
            status="ready" if complete else "needs_input",
            metadata=metadata,
            message=None if complete else "File thiếu thông tin họ model hoặc tác vụ.",
        )
    except Exception:
        traceback.print_exc(file=sys.stderr)
        trace = traceback.format_exc()[-8192:]
        result = InspectResult(
            status="failed",
            message="Không đọc được metadata. File có thể hỏng hoặc chưa được hỗ trợ.",
        )
    output = result.model_dump()
    if trace:
        output["traceback"] = trace
    print(json.dumps(output, allow_nan=False))


if __name__ == "__main__":
    main()
