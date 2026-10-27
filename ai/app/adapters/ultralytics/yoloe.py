"""Chuẩn bị text prompt YOLOE từ encoder local trước khi xử lý frame."""

import importlib.util
import os
from pathlib import Path
from typing import Any

ENCODERS = {"mobileclip:blt": "mobileclip_blt.ts", "mobileclip2:b": "mobileclip2_b.ts"}


# --------------------------- Thư mục encoder local ---------------------------
def encoder_directory() -> Path:
    """Trả storage encoder từ cấu hình hoặc data/yoloe; không tạo file hay tải mạng."""
    default = Path(__file__).resolve().parents[4] / "data" / "yoloe"
    return (
        Path(os.getenv("VISIONKIT_YOLOE_ENCODERS_PATH", str(default)))
        .expanduser()
        .resolve()
    )


# ------------------------------ Gán text prompt ------------------------------
def configure_text_prompts(model: Any, prompts: list[str], device: str) -> None:
    """Tạo embedding một lần trên thiết bị chạy và gán class theo đúng thứ tự prompt.

    Tham số: model YOLOE local, danh sách prompt đã kiểm tra và thiết bị thực tế.
    Ngoại lệ: ValueError khi checkpoint không đổi được prompt hoặc thiếu encoder.
    Tác động phụ: nạp TorchScript encoder local; thay embedding và tên class trong
    model của worker hiện tại. Không tải mạng, không sửa checkpoint trên đĩa.
    """
    head = model.model.model[-1]
    if hasattr(head, "lrpc") or getattr(head, "is_fused", False):
        raise ValueError(
            "Model prompt-free hoặc đã fuse không đổi được prompt. Chọn YOLOE text/visual .pt."
        )
    variant = getattr(model.model, "text_model", "mobileclip:blt")
    filename = ENCODERS.get(variant)
    if filename is None:
        raise ValueError("Text encoder của checkpoint YOLOE chưa được hỗ trợ.")
    encoder_path = encoder_directory() / filename
    if not encoder_path.is_file() or importlib.util.find_spec("clip") is None:
        raise ValueError(
            "Thiếu text encoder YOLOE. Chạy uv sync --locked và python -m app.inference.setup_yoloe --series all trong ai/."
        )
    from ultralytics.nn.text_model import MobileCLIPTS

    model.to(device)
    model.model.clip_model = MobileCLIPTS(device=device, weight=str(encoder_path))
    try:
        embeddings = model.model.get_text_pe(prompts, cache_clip_model=True)
        model.set_classes(prompts, embeddings)
    finally:
        # Chỉ giữ embedding; encoder không cần ở trong vòng lặp inference.
        del model.model.clip_model
