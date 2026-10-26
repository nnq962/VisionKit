"""Cấu hình đường dẫn, giới hạn upload và nguồn web được phép gọi API."""

import os
from dataclasses import dataclass
from pathlib import Path


# ----------------------------- Cấu hình backend ------------------------------
@dataclass(frozen=True)
class Settings:
    """Giữ cấu hình backend; cho phép truyền giá trị riêng khi kiểm thử.

    Thuộc tính:
        database_path: File SQLite, không thay đổi đường dẫn dữ liệu đã có.
        sources_path: Thư mục quản lý file nguồn được upload.
        ai_url: URL API nội bộ AI; None tắt tự động inspect trong unit test.
        runs_path: Thư mục snapshot tạm cho inference, mặc định data/runs.
        models_path: Thư mục model; mặc định cạnh thư mục sources.
        max_model_upload_bytes: Giới hạn dung lượng model upload.
        max_model_bytes: Giới hạn dung lượng một model khi tải.
        model_download_concurrency: Số lượt tải đồng thời trong một worker.
        max_upload_bytes: Kích thước tối đa của một ảnh, tính bằng byte.
        max_video_upload_bytes: Kích thước video tối đa, tính bằng byte.
        max_image_pixels: Số pixel tối đa trước khi giải mã ảnh.
        cors_origins: Các origin web được phép gọi API trực tiếp.
    """

    database_path: Path
    sources_path: Path
    models_path: Path | None = None
    ai_url: str | None = None
    runs_path: Path | None = None
    max_model_upload_bytes: int = 200 * 1024 * 1024
    max_model_bytes: int = 1024 * 1024 * 1024
    model_download_concurrency: int = 2
    max_upload_bytes: int = 20 * 1024 * 1024
    max_video_upload_bytes: int = 200 * 1024 * 1024
    max_image_pixels: int = 64_000_000
    cors_origins: tuple[str, ...] = ("http://localhost:3001", "http://localhost:3000")


# -------------------------- Đọc cấu hình môi trường --------------------------
def load_settings() -> Settings:
    """Đọc biến môi trường, trả cấu hình với đường dẫn tuyệt đối.

    Dữ liệu mặc định nằm trong data/ ở gốc monorepo. Biến VISIONKIT_DB_PATH
    tương thích cấu hình SQLite trước đây; VISIONKIT_SOURCES_PATH đổi nơi lưu ảnh.
    """
    root = Path(__file__).resolve().parents[3] / "data"
    return Settings(
        database_path=Path(
            os.getenv("VISIONKIT_DB_PATH", str(root / "visionkit.sqlite3"))
        )
        .expanduser()
        .resolve(),
        sources_path=Path(os.getenv("VISIONKIT_SOURCES_PATH", str(root / "sources")))
        .expanduser()
        .resolve(),
        runs_path=Path(os.getenv("VISIONKIT_RUNS_PATH", str(root / "runs")))
        .expanduser()
        .resolve(),
        ai_url=os.getenv("VISIONKIT_AI_URL", "http://127.0.0.1:8001").rstrip("/"),
        models_path=Path(os.getenv("VISIONKIT_MODELS_PATH", str(root / "models")))
        .expanduser()
        .resolve(),
        max_model_upload_bytes=int(os.getenv("VISIONKIT_MAX_MODEL_UPLOAD_MB", "200"))
        * 1024
        * 1024,
        max_video_upload_bytes=int(os.getenv("VISIONKIT_MAX_VIDEO_UPLOAD_MB", "200"))
        * 1024
        * 1024,
        cors_origins=tuple(
            origin.strip()
            for origin in os.getenv(
                "VISIONKIT_CORS_ORIGINS", "http://localhost:3001,http://localhost:3000"
            ).split(",")
            if origin.strip()
        ),
    )
