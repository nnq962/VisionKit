"""YouTube dùng dependency tùy chọn và phân biệt VOD/live khi mở."""

from dataclasses import replace

import numpy as np

from ..exceptions import MediaSourceError, StreamError
from ..models import SourceMeta, SourceType
from ..utils import source_label
from .video import VideoReader


# --------------------------- Đọc và quản lý source ---------------------------
class YoutubeReader(VideoReader):
    """Resolve URL lazy; VOD đọc tuần tự, live được AutoBatch chuyển sang latest-frame."""

    source_type = SourceType.YOUTUBE

    def __init__(self, source: str, *, vid_stride: int = 1) -> None:
        """Giữ URL gốc; chưa import yt-dlp hoặc kết nối mạng."""
        super().__init__(source, vid_stride=vid_stride)
        self._stream_url: str | None = None

    def open(self) -> "YoutubeReader":
        """Resolve một URL trong thời gian giới hạn; báo rõ dependency chưa cài."""
        if self._opened:
            return self
        try:
            import yt_dlp
        except ImportError as exc:
            raise MediaSourceError(
                "YouTube cần cài extra: uv sync --extra youtube."
            ) from exc
        try:
            with yt_dlp.YoutubeDL(
                {
                    "format": "best[ext=mp4]/best",
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "socket_timeout": 10,
                    "retries": 1,
                    "extractor_retries": 1,
                }
            ) as downloader:
                info = downloader.extract_info(self._source, download=False)
            if not info or not isinstance(info.get("url"), str):
                raise MediaSourceError("YouTube không trả stream URL đơn.")
            self._stream_url = info["url"]
            self.is_stream = bool(info.get("is_live"))
            self._fps_hint = float(info.get("fps") or 0)
            super().open()
        except BaseException:
            self.close()
            raise
        return self

    def _capture_target(self) -> str:
        """Trả URL đã resolve, không coi URL người dùng là đường dẫn local."""
        if not self._stream_url:
            raise MediaSourceError("Chưa resolve được YouTube.")
        return self._stream_url

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Gắn metadata YouTube; live không có tiến độ hoặc vị trí video hữu hạn."""
        result = super().read()
        if result is None:
            if self.is_stream:
                raise StreamError("YouTube live mất kết nối.")
            return None
        frame, meta = result
        return frame, replace(
            meta,
            name=source_label(self._source),
            is_stream=self.is_stream,
            total_frames=None if self.is_stream else meta.total_frames,
            timestamp_ms=None if self.is_stream else meta.timestamp_ms,
        )

    def close(self) -> None:
        """Đóng capture và quên signed URL để tránh giữ token ngoài vòng đời."""
        super().close()
        self._stream_url = None
