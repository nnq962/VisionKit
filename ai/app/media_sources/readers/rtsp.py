"""RTSP/RTMP qua FFMPEG với timeout và reconnect có thể ngắt."""

import math
import threading
import time
from urllib.parse import urlsplit

import cv2
import numpy as np

from ..exceptions import StreamError
from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr, open_capture, source_label
from .base import BaseReader


# --------------------------- Đọc và quản lý source ---------------------------
class RtspReader(BaseReader):
    """Một stream mạng; request_stop đánh thức backoff, thread đọc tự release."""

    source_type = SourceType.RTSP
    is_stream = True

    def __init__(
        self,
        source: str,
        *,
        reconnect: bool = True,
        reconnect_delay: float = 1.0,
        max_reconnect_attempts: int = 5,
        reconnect_forever: bool = False,
        open_timeout_ms: int = 5000,
        read_timeout_ms: int = 5000,
    ) -> None:
        """Kiểm tra URL/timeout; mặc định giới hạn số lần reconnect để không chờ vô hạn."""
        parsed = urlsplit(source)
        if (
            parsed.scheme.lower() not in {"rtsp", "rtsps", "rtmp", "rtmps"}
            or not parsed.hostname
        ):
            raise ValueError("URL stream không hợp lệ.")
        if not 0 < open_timeout_ms <= 60000 or not 0 < read_timeout_ms <= 60000:
            raise ValueError("Timeout stream không hợp lệ.")
        if not 0 <= reconnect_delay <= 60 or not 0 <= max_reconnect_attempts <= 100:
            raise ValueError("Cấu hình reconnect không hợp lệ.")
        super().__init__(source)
        self._reconnect = reconnect
        self._delay = reconnect_delay
        self._attempts = max_reconnect_attempts
        self._forever = reconnect_forever
        self._open_timeout = open_timeout_ms
        self._read_timeout = read_timeout_ms
        self._stop = threading.Event()
        self._cap: cv2.VideoCapture | None = None
        self._fps: float | None = None

    def _connect(self) -> None:
        """Mở capture có timeout và nhả capture ngay nếu không kết nối được."""
        cap = open_capture(self._source, self._open_timeout, self._read_timeout)
        try:
            if not cap.isOpened():
                raise StreamError("Không kết nối được stream.")
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            self._fps = fps if math.isfinite(fps) and fps > 0 else None
        except BaseException:
            cap.release()
            raise
        self._cap = cap

    def open(self) -> "RtspReader":
        """Kết nối lần đầu; reconnect lúc read sẽ dùng cùng chính sách timeout."""
        if self._opened:
            return self
        self._stop.clear()
        self._connect()
        self._frame_index = 0
        self._opened = True
        LOGGER.info("Đã kết nối stream %s.", source_label(self._source))
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Đọc frame hoặc reconnect; hết lượt thì raise, stop thì trả None."""
        self.ensure_open()
        attempt = 0
        while not self._stop.is_set():
            ok, frame = self._cap.read() if self._cap is not None else (False, None)
            if ok and frame is not None:
                frame = ensure_bgr(frame)
                height, width = frame.shape[:2]
                meta = SourceMeta(
                    source_label(self._source),
                    self.source_type,
                    self._frame_index,
                    (width, height),
                    fps=self._fps,
                    is_stream=True,
                    timestamp=time.time(),
                )
                self._frame_index += 1
                return frame, meta
            if not self._reconnect or (not self._forever and attempt >= self._attempts):
                raise StreamError("Stream mất kết nối; đã hết lượt thử lại.")
            if self._cap is not None:
                self._cap.release()
                self._cap = None
            delay = min(60.0, self._delay * 2 ** min(attempt, 6))
            attempt += 1
            LOGGER.warning(
                "Stream mất kết nối, thử lại lần %s: %s",
                attempt,
                source_label(self._source),
            )
            if self._stop.wait(delay):
                return None
            try:
                self._connect()
            except Exception:
                LOGGER.warning(
                    "Chưa kết nối lại được stream %s.", source_label(self._source)
                )
        return None

    def request_stop(self) -> None:
        """Ngắt chờ reconnect; không release capture đang read."""
        self._stop.set()

    def close(self) -> None:
        """Đánh dấu stop và giải phóng capture trong thread sở hữu."""
        self._stop.set()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False
