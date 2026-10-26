"""Phân loại nguồn; chỉ hỗ trợ URL thuộc reader mạng cụ thể."""

from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from .models import SourceType

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
    ".gif",
    ".avif",
    ".heic",
    ".heif",
}
VIDEO_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".flv",
    ".wmv",
    ".m4v",
    ".webm",
    ".ogv",
}


# --------------------------- Đọc và quản lý source ---------------------------
def classify_source(source: object) -> SourceType:
    """Nhận int, Path, URL hoặc ndarray; không đoán mọi URL là video local."""
    if isinstance(source, bool):
        raise ValueError("Boolean không phải device id.")
    if isinstance(source, int):
        if source < 0:
            raise ValueError("Device id không được âm.")
        return SourceType.WEBCAM
    if isinstance(source, np.ndarray):
        return SourceType.IMAGE
    if isinstance(source, (str, Path)):
        text = str(source)
        parsed = urlsplit(text)
        host = (parsed.hostname or "").lower()
        if parsed.scheme.lower() in {"rtsp", "rtsps", "rtmp", "rtmps"} and host:
            return SourceType.RTSP
        if parsed.scheme.lower() in {"https", "http"} and (
            host in {"youtube.com", "youtu.be", "youtube-nocookie.com"}
            or host.endswith(".youtube.com")
        ):
            return SourceType.YOUTUBE
        if parsed.scheme and "://" in text:
            raise ValueError("URL không thuộc loại source được hỗ trợ.")
        suffix = Path(text).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            return SourceType.IMAGE
        if suffix in VIDEO_EXTENSIONS:
            return SourceType.VIDEO
    raise ValueError("Không nhận diện được loại source.")
