"""Đọc ảnh bằng Pillow để giữ EXIF và HEIC/HEIF như pipeline hiện có."""

import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from ..exceptions import MediaSourceError
from ..models import SourceMeta, SourceType
from ..utils import LOGGER, MAX_IMAGE_PIXELS, ensure_bgr
from .base import BaseReader


# --------------------------- Đọc và quản lý source ---------------------------
class ImageReader(BaseReader):
    """Đọc một ảnh local/ndarray một lần; giữ frame đến close hoặc lần read đó."""

    source_type = SourceType.IMAGE

    def __init__(self, source: str | Path | np.ndarray) -> None:
        """Lưu nguồn; chưa giải mã ảnh."""
        super().__init__(source)
        self._frame: np.ndarray | None = None
        self._meta: SourceMeta | None = None

    def open(self) -> "ImageReader":
        """Đọc local bằng Pillow, kiểm tra pixel trước khi load và chỉnh hướng EXIF."""
        if self._opened:
            return self
        if isinstance(self._source, np.ndarray):
            frame = ensure_bgr(self._source)
            name = "array"
        else:
            from pillow_heif import register_heif_opener

            register_heif_opener()
            try:
                with Image.open(self._source) as image:
                    if image.width * image.height > MAX_IMAGE_PIXELS:
                        raise MediaSourceError("Ảnh quá lớn.")
                    oriented = ImageOps.exif_transpose(image)
                    try:
                        with oriented.convert("RGB") as rgb:
                            frame = cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2BGR)
                    finally:
                        oriented.close()
            except (
                OSError,
                ImportError,
                UnidentifiedImageError,
                Image.DecompressionBombError,
            ) as exc:
                # Ultralytics có thể bọc Image.open rồi import codec phụ khi
                # ảnh hỏng. Thiếu codec vẫn là lỗi đọc source, không phải model.
                raise MediaSourceError("Không đọc được ảnh.") from exc
            name = Path(self._source).name
        height, width = frame.shape[:2]
        self._frame = frame
        self._meta = SourceMeta(
            name, self.source_type, 0, (width, height), timestamp=time.time()
        )
        self._opened = True
        self._frame_index = 0
        LOGGER.info("Đã đọc ảnh %s (%s × %s).", name, width, height)
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Trả frame duy nhất, nhả tham chiếu nội bộ ngay sau khi consumer nhận."""
        self.ensure_open()
        if self._frame is None or self._meta is None:
            return None
        result = self._frame, self._meta
        self._frame = None
        self._meta = None
        self._frame_index += 1
        return result

    def close(self) -> None:
        """Nhả frame/metadata, cho phép mở lại tường minh."""
        self._frame = None
        self._meta = None
        self._opened = False
