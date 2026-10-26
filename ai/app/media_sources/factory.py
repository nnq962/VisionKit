"""Tạo reader lazy; dependency YouTube không bắt buộc với ảnh/video/camera."""

from collections.abc import Iterable
from itertools import islice
from pathlib import Path
from typing import Any

import numpy as np

from .batch import AutoBatchReader, StreamBatchReader, SyncBatchReader, _BaseBatch
from .detector import classify_source
from .models import SourceType
from .readers.base import BaseReader
from .readers.image import ImageReader
from .readers.rtsp import RtspReader
from .readers.video import VideoReader
from .readers.webcam import WebcamReader
from .readers.youtube import YoutubeReader

READERS = {
    SourceType.IMAGE: ImageReader,
    SourceType.VIDEO: VideoReader,
    SourceType.WEBCAM: WebcamReader,
    SourceType.RTSP: RtspReader,
    SourceType.YOUTUBE: YoutubeReader,
}


# --------------------------- Đọc và quản lý source ---------------------------
def is_sequence(value: object) -> bool:
    """Phân biệt iterable nhiều nguồn với ndarray/string/Path là nguồn đơn."""
    return isinstance(value, Iterable) and not isinstance(
        value, (str, bytes, bytearray, Path, np.ndarray)
    )


# --------------------------- Đọc và quản lý source ---------------------------
def create_media_source(
    sources: Any, *, source_type: SourceType | None = None, **kwargs: Any
) -> BaseReader | _BaseBatch:
    """Tạo nguồn đơn/batch đồng nhất; kwargs sai được báo lỗi, không âm thầm bỏ qua.

    source_type cho adapter biết loại từ hợp đồng API dù file không có đuôi.
    Batch giữ tối đa 16 nguồn; nguồn mạng chỉ được mở tường minh qua reader mạng.
    """
    batch = is_sequence(sources)
    items = list(islice(iter(sources), 17)) if batch else [sources]
    if not items or len(items) > 16:
        raise ValueError("Batch cần từ 1 đến 16 nguồn.")
    kinds = [
        SourceType(source_type) if source_type is not None else classify_source(item)
        for item in items
    ]
    if len(set(kinds)) != 1:
        raise ValueError("Batch phải cùng một loại source.")
    kind = kinds[0]
    readers = [READERS[kind](item, **kwargs) for item in items]
    if not batch:
        return readers[0]
    if kind == SourceType.YOUTUBE:
        return AutoBatchReader(readers)
    cls = StreamBatchReader if readers[0].is_stream else SyncBatchReader
    return cls(readers)
