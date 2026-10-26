"""Video tuần tự, bỏ decode frame không cần suy luận và giữ timeline gốc."""

import math
import time
from pathlib import Path

import cv2
import numpy as np

from ..exceptions import MediaSourceError
from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr, open_capture, source_label
from .base import BaseReader


# --------------------------- Đọc và quản lý source ---------------------------
class VideoReader(BaseReader):
    """Đọc một video với stride; read không pacing, AI runner quyết định nhịp."""

    source_type = SourceType.VIDEO

    def __init__(self, source: str | Path, *, vid_stride: int = 1) -> None:
        """Lưu đường dẫn và stride nguyên dương; không mở nguồn."""
        if (
            isinstance(vid_stride, bool)
            or not isinstance(vid_stride, int)
            or vid_stride < 1
        ):
            raise ValueError("vid_stride phải là số nguyên dương.")
        super().__init__(str(source))
        self._stride = vid_stride
        self._cap: cv2.VideoCapture | None = None
        self._fps = 0.0
        self._fps_hint = 0.0
        self._total = 0
        self._last_timestamp = -1.0

    def _capture_target(self) -> str:
        """Chỉ chấp nhận file tồn tại; YouTube override để resolve URL riêng."""
        if not Path(self._source).is_file():
            raise MediaSourceError("Video local không tồn tại.")
        return self._source

    def open(self) -> "VideoReader":
        """Mở FFMPEG có timeout, kiểm tra metadata và tự đóng nếu khởi tạo lỗi."""
        if self._opened:
            return self
        cap = open_capture(self._capture_target(), 5000, 5000)
        try:
            if not cap.isOpened():
                raise MediaSourceError("Không mở được video.")
            cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if not math.isfinite(fps) or not 0 < fps < 1000:
                fps = self._fps_hint
            if not math.isfinite(fps) or not 0 < fps < 1000:
                raise MediaSourceError("Không xác định được frame rate video.")
            total = float(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self._fps = fps
            self._total = max(0, int(total)) if math.isfinite(total) else 0
        except BaseException:
            cap.release()
            raise
        self._cap = cap
        self._frame_index = 0
        self._last_timestamp = -1.0
        self._opened = True
        LOGGER.info("Đã mở video %s (%.1f FPS).", source_label(self._source), fps)
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Grab mọi frame, retrieve theo stride; giữ PTS nếu hợp lệ, fallback index/FPS."""
        self.ensure_open()
        while self._cap.grab():
            index = self._frame_index
            self._frame_index += 1
            if index % self._stride:
                continue
            ok, frame = self._cap.retrieve()
            if not ok or frame is None:
                raise MediaSourceError("Không giải mã được frame video.")
            frame = ensure_bgr(frame)
            pts = float(self._cap.get(cv2.CAP_PROP_POS_MSEC))
            if (
                not math.isfinite(pts)
                or pts < 0
                or (index > 0 and pts <= self._last_timestamp)
            ):
                pts = index / self._fps * 1000
            pts = max(pts, self._last_timestamp)
            self._last_timestamp = pts
            height, width = frame.shape[:2]
            meta = SourceMeta(
                Path(self._source).name,
                self.source_type,
                index,
                (width, height),
                fps=self._fps,
                total_frames=self._total or None,
                timestamp=time.time(),
                timestamp_ms=pts,
            )
            return frame, meta
        if self._total and self._frame_index < self._total:
            raise MediaSourceError("Video bị gián đoạn trước khi đọc hết frame.")
        return None

    def close(self) -> None:
        """Đóng capture idempotent khi hết nguồn, consumer lỗi hoặc huỷ lượt chạy."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._opened = False
