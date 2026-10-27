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

    def __init__(self, source: int, *, warmup_seconds: float = 0) -> None:
        """Giữ index và warmup_seconds (0–3 giây); chưa mở camera, mặc định không warmup."""
        if isinstance(source, bool) or not isinstance(source, int) or source < 0:
            raise ValueError("Webcam cần device id không âm.")
        if not math.isfinite(warmup_seconds) or not 0 <= warmup_seconds <= 3:
            raise ValueError("Thời gian ổn định webcam phải từ 0 đến 3 giây.")
        self._warmup_seconds = warmup_seconds
        super().__init__(source)
        self._cap: cv2.VideoCapture | None = None
        self._fps: float | None = None

    def open(self) -> "WebcamReader":
        """Mở webcam, bỏ frame khởi động nếu có warmup để auto-exposure ổn định; lỗi luôn release."""
        if self._opened:
            return self
        cap = cv2.VideoCapture(self._source)
        try:
            if not cap.isOpened():
                raise StreamError("Không mở được webcam.")
            if self._warmup_seconds:
                started = time.monotonic()
                valid = 0
                for _ in range(90):
                    ok, frame = cap.read()
                    if ok and frame is not None:
                        valid += 1
                    if (
                        valid >= 6
                        and time.monotonic() - started >= self._warmup_seconds
                    ):
                        break
                if valid < 6:
                    raise StreamError("Webcam chưa trả frame ổn định.")
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
