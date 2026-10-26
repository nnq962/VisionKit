"""Chuẩn hóa frame và tạo capture; không cấu hình lại logger của ứng dụng."""

import logging
from urllib.parse import urlsplit, urlunsplit

import cv2
import numpy as np

from .exceptions import MediaSourceError

LOGGER = logging.getLogger(__name__.rsplit(".", 1)[0])
MAX_IMAGE_PIXELS = 64_000_000


# --------------------------- Đọc và quản lý source ---------------------------
def source_label(source: object) -> str:
    """Che user/password và query URL khi ghi log hoặc tạo metadata."""
    text = str(source)
    parsed = urlsplit(text)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.rsplit("@", 1)[-1]
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    return text


# --------------------------- Đọc và quản lý source ---------------------------
def ensure_bgr(frame: np.ndarray) -> np.ndarray:
    """Nhận uint8 BGR/gray/BGRA; trả mảng BGR liên tục, từ chối ảnh quá lớn/rỗng."""
    if not isinstance(frame, np.ndarray) or frame.dtype != np.uint8:
        raise MediaSourceError("Frame phải là ndarray uint8.")
    if frame.ndim not in (2, 3) or not frame.size:
        raise MediaSourceError("Kích thước frame không hợp lệ.")
    if frame.shape[0] * frame.shape[1] > MAX_IMAGE_PIXELS:
        raise MediaSourceError("Ảnh quá lớn.")
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.shape[2] == 1:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.shape[2] == 4:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    elif frame.shape[2] != 3:
        raise MediaSourceError("Frame phải có 1, 3 hoặc 4 channel.")
    return np.ascontiguousarray(frame)


# --------------------------- Đọc và quản lý source ---------------------------
def open_capture(
    source: str, open_timeout_ms: int, read_timeout_ms: int
) -> cv2.VideoCapture:
    """Mở FFMPEG với timeout; không fallback sang kết nối không có timeout."""
    return cv2.VideoCapture(
        source,
        cv2.CAP_FFMPEG,
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            open_timeout_ms,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            read_timeout_ms,
        ],
    )
