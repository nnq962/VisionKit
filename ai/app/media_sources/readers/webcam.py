"""Webcam trên máy chạy AI; không phải camera trình duyệt."""

import math
import time

import cv2
import numpy as np

from ..exceptions import StreamError
from ..models import SourceMeta, SourceType
from ..utils import ensure_bgr
from .base import BaseReader


# --------------------------- Đọc và quản lý source ---------------------------
class WebcamReader(BaseReader):
    """Đọc webcam; batch chịu trách nhiệm thread nền và giới hạn thời gian đóng."""

    source_type = SourceType.WEBCAM
    is_stream = True

    def __init__(self, source: int) -> None:
        """Lưu device id không âm; không chiếm camera lúc khởi tạo."""
        if isinstance(source, bool) or not isinstance(source, int) or source < 0:
            raise ValueError("Webcam cần device id không âm.")
        super().__init__(source)
        self._cap: cv2.VideoCapture | None = None
        self._fps: float | None = None

    def open(self) -> "WebcamReader":
        """Mở webcam; không truyền timeout FFMPEG vào backend webcam."""
        if self._opened:
            return self
        cap = cv2.VideoCapture(self._source)
        try:
            if not cap.isOpened():
                raise StreamError("Không mở được webcam.")
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            self._fps = fps if math.isfinite(fps) and fps > 0 else None
        except BaseException:
            cap.release()
            raise
        self._cap = cap
        self._frame_index = 0
        self._opened = True
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta]:
        """Đọc frame BGR; mất tín hiệu là lỗi thay vì kết thúc thành công."""
        self.ensure_open()
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise StreamError("Webcam mất tín hiệu.")
        frame = ensure_bgr(frame)
        height, width = frame.shape[:2]
        meta = SourceMeta(
            f"webcam_{self._source}",
            self.source_type,
            self._frame_index,
            (width, height),
            fps=self._fps,
            is_stream=True,
            timestamp=time.time(),
        )
        self._frame_index += 1
        return frame, meta

    def close(self) -> None:
        """Chỉ thread sở hữu được release capture; gọi lặp lại an toàn."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False
