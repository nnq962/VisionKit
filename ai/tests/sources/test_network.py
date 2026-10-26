"""Kiểm thử lifecycle RTSP/webcam/YouTube bằng capture giả, không truy cập mạng."""

import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from app.media_sources import MediaSourceError, StreamError
from app.media_sources.readers.rtsp import RtspReader
from app.media_sources.readers.webcam import WebcamReader
from app.media_sources.readers.youtube import YoutubeReader


# --------------------------- Kiểm thử RTSP -----------------------------------
class RtspTests(unittest.TestCase):
    """Reconnect giới hạn, cancel nhanh và không log thông tin xác thực."""

    def test_failed_connection_and_metadata_release_capture(self) -> None:
        """Mở lỗi hoặc metadata lỗi đều nhả capture trước khi trả lỗi."""
        for failure in ["open", "metadata"]:
            cap = Mock()
            cap.isOpened.return_value = failure != "open"
            if failure == "metadata":
                cap.get.side_effect = RuntimeError("metadata")
            with patch("app.media_sources.readers.rtsp.open_capture", return_value=cap):
                with self.assertRaises((StreamError, RuntimeError)):
                    RtspReader("rtsp://cam/live").open()
            cap.release.assert_called_once()

    def test_reconnect_returns_frame_and_redacts_logs(self) -> None:
        """Mất một kết nối rồi nhận frame mới; cap cũ được đóng và credentials bị che."""
        failed, recovered = Mock(), Mock()
        for cap in [failed, recovered]:
            cap.isOpened.return_value = True
            cap.get.return_value = 24
        failed.read.return_value = False, None
        recovered.read.return_value = True, np.zeros((8, 9, 3), dtype=np.uint8)
        with (
            patch(
                "app.media_sources.readers.rtsp.open_capture",
                side_effect=[failed, recovered],
            ),
            self.assertLogs("app.media_sources", level="INFO") as logs,
        ):
            with RtspReader(
                "rtsp://user:secret@cam/live?token=private", reconnect_delay=0
            ) as reader:
                frame, meta = reader.read()
                self.assertEqual(frame.shape, (8, 9, 3))
                self.assertEqual(meta.name, "rtsp://cam/live")
                self.assertIsNone(meta.timestamp_ms)
                self.assertEqual(meta.frame_index, 0)
        failed.release.assert_called_once()
        recovered.release.assert_called_once()
        self.assertNotIn("secret", " ".join(logs.output))
        self.assertNotIn("private", " ".join(logs.output))

    def test_reconnect_exhaustion_is_failure(self) -> None:
        """Hết số lần thử lại không bị coi là kết thúc nguồn thành công."""
        caps = [Mock(), Mock(), Mock()]
        for cap in caps:
            cap.isOpened.return_value = True
            cap.get.return_value = 24
            cap.read.return_value = False, None
        with patch(
            "app.media_sources.readers.rtsp.open_capture", side_effect=caps
        ) as connect:
            with RtspReader(
                "rtsp://cam/live", reconnect_delay=0, max_reconnect_attempts=2
            ) as reader:
                with self.assertRaises(StreamError):
                    reader.read()
            self.assertEqual(connect.call_count, 3)
        for cap in caps:
            cap.release.assert_called_once()

    def test_stop_wakes_reconnect_backoff(self) -> None:
        """Stop không đợi hết delay 30 giây hoặc release cap trong lúc read."""
        cap = Mock()
        cap.isOpened.return_value = True
        cap.get.return_value = 24
        entered = threading.Event()

        def fail_read() -> tuple[bool, None]:
            """Đánh dấu lần read đầu để test chỉ dừng sau khi reader đã mở."""
            entered.set()
            return False, None

        cap.read.side_effect = fail_read
        with patch("app.media_sources.readers.rtsp.open_capture", return_value=cap):
            reader = RtspReader("rtsp://cam/live", reconnect_delay=30)
            reader.open()
            results = []

            def consume() -> None:
                """Thread giữ quyền sở hữu capture và tự thu hồi khi kết thúc."""
                try:
                    results.append(reader.read())
                finally:
                    reader.close()

            thread = threading.Thread(target=consume)
            thread.start()
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            reader.request_stop()
            thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertLess(time.monotonic() - started, 1)
            self.assertEqual(results, [None])
        cap.release.assert_called_once()

    def test_validation(self) -> None:
        """Từ chối URL sai và timeout/backoff không hữu hạn hoặc âm."""
        for kwargs in [
            {"read_timeout_ms": 0},
            {"open_timeout_ms": float("inf")},
            {"reconnect_delay": float("nan")},
            {"max_reconnect_attempts": -1},
        ]:
            with self.assertRaises(ValueError):
                RtspReader("rtsp://cam/live", **kwargs)
        with self.assertRaises(ValueError):
            RtspReader("https://other.test/live")


# --------------------------- Kiểm thử webcam ---------------------------------
class WebcamTests(unittest.TestCase):
    """Webcam vẫn dùng capture mặc định, không thêm params của FFMPEG."""

    def test_success_disconnect_and_cleanup(self) -> None:
        """Metadata BGR đúng và mất tín hiệu phải báo lỗi, capture chỉ release một lần."""
        cap = Mock()
        cap.isOpened.return_value = True
        cap.get.return_value = float("nan")
        cap.read.side_effect = [(True, np.zeros((8, 9), dtype=np.uint8)), (False, None)]
        with patch(
            "app.media_sources.readers.webcam.cv2.VideoCapture", return_value=cap
        ) as capture:
            with WebcamReader(0) as reader:
                reader.open()
                frame, meta = reader.read()
                self.assertEqual(frame.shape, (8, 9, 3))
                self.assertIsNone(meta.fps)
                with self.assertRaises(StreamError):
                    reader.read()
            reader.close()
            capture.assert_called_once_with(0)
        cap.release.assert_called_once()

    def test_failed_open_releases_capture(self) -> None:
        """Không chiếm thiết bị khi open webcam lỗi."""
        cap = Mock()
        cap.isOpened.return_value = False
        with patch(
            "app.media_sources.readers.webcam.cv2.VideoCapture", return_value=cap
        ):
            with self.assertRaises(StreamError):
                WebcamReader(0).open()
        cap.release.assert_called_once()


# --------------------------- Kiểm thử YouTube --------------------------------
class YoutubeTests(unittest.TestCase):
    """Resolver là dependency tùy chọn; không cần tài khoản/mạng cho test."""

    def test_missing_optional_dependency_is_actionable(self) -> None:
        """Ảnh/video không phụ thuộc yt-dlp; mở YouTube báo rõ extra cần cài."""
        with patch.dict("sys.modules", {"yt_dlp": None}):
            with self.assertRaisesRegex(MediaSourceError, "--extra youtube"):
                YoutubeReader("https://youtu.be/fixture").open()

    def test_resolver_lazy_limits_network_and_marks_live(self) -> None:
        """Resolve có socket timeout và không tải playlist; live không có phần trăm/PTS."""
        downloader = Mock()
        downloader.__enter__ = Mock(return_value=downloader)
        downloader.__exit__ = Mock(return_value=False)
        downloader.extract_info.return_value = {
            "url": "https://cdn.test/signed?token=secret",
            "is_live": True,
        }
        library = types.ModuleType("yt_dlp")
        library.YoutubeDL = Mock(return_value=downloader)
        cap = Mock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 24,
            cv2.CAP_PROP_FRAME_COUNT: 0,
            cv2.CAP_PROP_POS_MSEC: 0,
        }[prop]
        cap.grab.return_value = True
        cap.retrieve.return_value = True, np.zeros((8, 9, 3), dtype=np.uint8)
        with (
            patch.dict("sys.modules", {"yt_dlp": library}),
            patch(
                "app.media_sources.readers.video.open_capture", return_value=cap
            ) as capture,
        ):
            reader = YoutubeReader("https://youtu.be/fixture")
            library.YoutubeDL.assert_not_called()
            with reader:
                frame, meta = reader.read()
                self.assertTrue(reader.is_stream)
                self.assertIsNone(meta.total_frames)
                self.assertIsNone(meta.timestamp_ms)
                self.assertEqual(meta.source_type.value, "youtube")
            self.assertIsNone(reader._stream_url)
            self.assertEqual(
                capture.call_args.args[0], "https://cdn.test/signed?token=secret"
            )
        cap.release.assert_called_once()
        self.assertEqual(library.YoutubeDL.call_args.args[0]["socket_timeout"], 10)
        self.assertTrue(library.YoutubeDL.call_args.args[0]["noplaylist"])
