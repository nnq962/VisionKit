"""Cấu hình API nội bộ và thư mục model được backend/AI dùng chung."""

import os
from dataclasses import dataclass
from pathlib import Path


# -------------------------------- Cấu hình AI --------------------------------
@dataclass(frozen=True)
class Settings:
    """Giữ models_path được phép đọc và timeout cho mỗi tiến trình kiểm tra."""

    models_path: Path
    inspect_timeout: float = 90
    max_model_bytes: int = 1024 * 1024 * 1024


# ------------------------------- Đọc cấu hình --------------------------------
def load_settings() -> Settings:
    """Đọc VISIONKIT_MODELS_PATH dùng chung backend; mặc định data/models ở gốc repo."""
    root = Path(__file__).resolve().parents[3] / "data" / "models"
    return Settings(
        models_path=Path(os.getenv("VISIONKIT_MODELS_PATH", str(root)))
        .expanduser()
        .resolve()
    )
