"""Kiểm thử ảnh/video thật và cleanup trong các nhánh lỗi."""

import gc
import subprocess
import sys
import tempfile
import unittest
import weakref
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image
from pillow_heif import register_heif_opener

from app.media_sources import (
    MediaSourceError,
    MediaSources,
    SourceType,
    create_media_source,
)
from app.media_sources.detector import classify_source
from app.media_sources.readers.image import ImageReader
from app.media_sources.readers.video import VideoReader
from app.media_sources.utils import ensure_bgr, open_capture, source_label


# -------------------------- Kiểm thử factory --------------------------------
class FactoryTests(unittest.TestCase):
    """Import không có tác dụng phụ; không âm thầm bỏ qua cấu hình viết sai."""

    def test_import_is_optional_and_logging_is_unchanged(self) -> None:
        """Không đòi yt-dlp/pytz/colorlog hay thay root logger khi import."""
        code = """import sys,logging
before = list(logging.getLogger().handlers)
import app.media_sources
assert before == logging.getLogger().handlers
assert not any(name in sys.modules for name in ['yt_dlp','pytz','colorlog'])
"""
        subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)

    def test_detection_validation_and_lazy_open(self) -> None:
        """Nhận codec hiện có, từ chối URL lạ, batch quá lớn/trộn loại và typo kwargs."""
        for suffix in ["heic", "heif", "avif", "gif", "png"]:
            self.assertEqual(classify_source("x." + suffix), SourceType.IMAGE)
        for suffix in ["webm", "ogv", "mp4"]:
            self.assertEqual(classify_source("x." + suffix), SourceType.VIDEO)
        self.assertEqual(classify_source("rtsps://user:pass@cam/live"), SourceType.RTSP)
        self.assertEqual(classify_source("https://youtu.be/abc"), SourceType.YOUTUBE)
        for source in [True, -1, "https://other.test/x.mp4", "unknown", []]:
            with self.assertRaises(ValueError):
                classify_source(source)
        for sources in [
            [],
            ["x.png", "y.mp4"],
            ["x.png"] * 17,
            (str(i) + ".png" for i in range(100)),
        ]:
            with self.assertRaises(ValueError):
                MediaSources(sources)
        with self.assertRaises(TypeError):
            create_media_source("x.mp4", typo_stride=2)
        with patch("app.media_sources.readers.video.open_capture") as capture:
            create_media_source("x.mp4")
            capture.assert_not_called()

    def test_redaction_and_timeout_no_unsafe_fallback(self) -> None:
        """Che password/token URL; backend từ chối timeout không được fallback bỏ timeout."""
        self.assertEqual(
            source_label("rtsp://user:secret@cam/live?token=secret"), "rtsp://cam/live"
        )
        with patch(
            "app.media_sources.utils.cv2.VideoCapture",
            side_effect=cv2.error("unsupported"),
        ) as capture:
            with self.assertRaises(cv2.error):
                open_capture("rtsp://cam/live", 100, 200)
            self.assertEqual(capture.call_count, 1)
            self.assertEqual(
                capture.call_args.args[2],
                [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                    100,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                    200,
                ],
            )


# ----------------------------- Kiểm thử ảnh ---------------------------------
class ImageReaderTests(unittest.TestCase):
    """Giữ màu BGR, EXIF, codec thật và giới hạn bộ nhớ."""

    def test_real_formats_and_exif(self) -> None:
        """Đọc PNG/HEIC/AVIF/GIF thật; chỉnh hướng EXIF trước suy luận."""
        register_heif_opener()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for suffix, fmt in [
                ("png", "PNG"),
                ("heic", "HEIF"),
                ("avif", "AVIF"),
                ("gif", "GIF"),
            ]:
                path = root / ("image." + suffix)
                Image.new("RGB", (24, 12), (255, 0, 0)).save(path, format=fmt)
                with MediaSources(path) as source:
                    frames, metas = next(source)
                    self.assertEqual(metas[0].resolution, (24, 12))
                    self.assertGreater(int(frames[0][0, 0, 2]), 240)
                    self.assertLess(int(frames[0][0, 0, 0]), 15)
                    self.assertEqual(list(source), [])
            path = root / "rotated.jpg"
            exif = Image.Exif()
            exif[274] = 6
            Image.new("RGB", (24, 12), "red").save(path, exif=exif)
            with ImageReader(path) as reader:
                frame, meta = next(reader)
                self.assertEqual(frame.shape[:2], (24, 12))
                self.assertEqual(meta.resolution, (12, 24))

    def test_array_validation(self) -> None:
        """Gray/alpha đổi thành BGR; reject dtype, channel và ảnh rỗng/quá lớn."""
        for shape in [(8, 9), (8, 9, 1), (8, 9, 3), (8, 9, 4)]:
            frame = ensure_bgr(np.zeros(shape, dtype=np.uint8))
            self.assertEqual(frame.shape, (8, 9, 3))
            self.assertTrue(frame.flags.c_contiguous)
        self.assertTrue(
            ensure_bgr(np.zeros((8, 9, 3), dtype=np.uint8)[:, ::2]).flags.c_contiguous
        )
        for frame in [
            np.zeros((8, 9, 2), dtype=np.uint8),
            np.zeros((0, 9, 3), dtype=np.uint8),
            np.zeros((8, 9, 3)),
            np.zeros(8, dtype=np.uint8),
        ]:
            with self.assertRaises(MediaSourceError):
                ensure_bgr(frame)
        with patch("app.media_sources.utils.MAX_IMAGE_PIXELS", 10):
            with self.assertRaises(MediaSourceError):
                ensure_bgr(np.zeros((8, 9, 3), dtype=np.uint8))

    def test_pixel_limit_and_broken_file(self) -> None:
        """Kiểm tra giới hạn trước decode và chuyển lỗi codec thành lỗi source."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "x.png"
            Image.new("RGB", (20, 20)).save(path)
            with patch("app.media_sources.readers.image.MAX_IMAGE_PIXELS", 100):
                with self.assertRaises(MediaSourceError):
                    ImageReader(path).open()
            path.write_bytes(b"bad")
            with self.assertRaises(MediaSourceError):
                ImageReader(path).open()
            with patch(
                "app.media_sources.readers.image.Image.open",
                side_effect=ImportError("optional codec missing"),
            ):
                with self.assertRaisesRegex(MediaSourceError, "Không đọc được ảnh"):
                    ImageReader(path).open()

    def test_decoded_image_is_not_retained(self) -> None:
        """Sau read, reader không giữ frame; close/open lặp lại an toàn."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "x.png"
            Image.new("RGB", (20, 20)).save(path)
            reader = ImageReader(path)
            reader.open()
            reader.open()
            frame, _ = next(reader)
            reference = weakref.ref(frame)
            del frame
            gc.collect()
            self.assertIsNone(reference())
            self.assertIsNone(reader.read())
            reader.close()
            reader.close()
            with reader:
                self.assertEqual(next(reader)[0].shape, (20, 20, 3))


# ---------------------------- Kiểm thử video --------------------------------
class VideoReaderTests(unittest.TestCase):
    """Kiểm tra stride/timeline và nhả capture khi mở/giải mã thất bại."""

    def test_real_video_stride_and_timestamp(self) -> None:
        """Stride giữ index/timeline video; iterator hết không tự mở video từ đầu."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clip.mp4"
            writer = cv2.VideoWriter(
                str(path), cv2.VideoWriter_fourcc(*"mp4v"), 100, (32, 32)
            )
            self.assertTrue(writer.isOpened())
            for _ in range(6):
                writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
            writer.release()
            with MediaSources(path, vid_stride=2) as source:
                metas = [metadata[0] for _, metadata in source]
            self.assertEqual([m.frame_index for m in metas], [0, 2, 4])
            np.testing.assert_allclose(
                [m.timestamp_ms for m in metas], [0, 20, 40], atol=0.1
            )
            self.assertEqual(metas[0].total_frames, 6)
            self.assertEqual(metas[0].fps, 100)
            self.assertEqual(list(source), [])

    def test_failed_open_releases_capture(self) -> None:
        """Capture chưa mở, FPS NaN, get lỗi đều phải release."""
        for mode in ["not_open", "nan", "get_error"]:
            cap = Mock()
            cap.isOpened.return_value = mode != "not_open"
            cap.get.return_value = float("nan")
            if mode == "get_error":
                cap.get.side_effect = RuntimeError("metadata")
            with (
                patch.object(VideoReader, "_capture_target", return_value="fixture"),
                patch("app.media_sources.readers.video.open_capture", return_value=cap),
            ):
                with self.assertRaises((MediaSourceError, RuntimeError)):
                    VideoReader("x.mp4").open()
            cap.release.assert_called_once()

    def test_retrieve_failure_early_eof_and_pts_fallback(self) -> None:
        """Video hỏng không báo completed; PTS lỗi dùng index/FPS."""
        cap = Mock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 10,
            cv2.CAP_PROP_FRAME_COUNT: 4,
            cv2.CAP_PROP_POS_MSEC: float("nan"),
        }[prop]
        cap.grab.side_effect = [True, True, False]
        cap.retrieve.return_value = (True, np.zeros((4, 4, 3), dtype=np.uint8))
        with (
            patch.object(VideoReader, "_capture_target", return_value="fixture"),
            patch("app.media_sources.readers.video.open_capture", return_value=cap),
        ):
            with self.assertRaises(MediaSourceError):
                with VideoReader("x.mp4") as reader:
                    self.assertEqual(next(reader)[1].timestamp_ms, 0)
                    self.assertEqual(next(reader)[1].timestamp_ms, 100)
                    next(reader)
        cap.release.assert_called_once()
        cap.reset_mock()
        cap.grab.side_effect = None
        cap.grab.return_value = True
        cap.retrieve.return_value = (False, None)
        with (
            patch.object(VideoReader, "_capture_target", return_value="fixture"),
            patch("app.media_sources.readers.video.open_capture", return_value=cap),
        ):
            with self.assertRaises(MediaSourceError):
                with VideoReader("x.mp4") as reader:
                    next(reader)
        cap.release.assert_called_once()

    def test_invalid_stride_and_network_boundary(self) -> None:
        """Reader local không mở URL tuỳ ý dù source_type được truyền tường minh."""
        for stride in [True, 0, -1, 1.5]:
            with self.assertRaises(ValueError):
                VideoReader("x.mp4", vid_stride=stride)
        with patch("app.media_sources.readers.video.open_capture") as capture:
            with self.assertRaises(MediaSourceError):
                VideoReader("https://other.test/x.mp4").open()
            capture.assert_not_called()

    def test_repeated_real_file_cycles_keep_descriptor_count(self) -> None:
        """50 chu kỳ ảnh/video thật không tăng FD, kể cả consumer dừng sớm."""
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "fixture.png"
            video = Path(temporary) / "fixture.mp4"
            Image.new("RGB", (32, 32)).save(image)
            writer = cv2.VideoWriter(
                str(video), cv2.VideoWriter_fourcc(*"mp4v"), 25, (32, 32)
            )
            self.assertTrue(writer.isOpened())
            for _ in range(3):
                writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
            writer.release()
            descriptor_path = Path("/proc/self/fd")
            before = (
                len(list(descriptor_path.iterdir()))
                if descriptor_path.exists()
                else None
            )
            references = []
            for _ in range(50):
                for path in [image, video]:
                    with MediaSources(path) as source:
                        frames, _ = next(source)
                        references.append(weakref.ref(frames[0]))
                        del frames
            gc.collect()
            self.assertTrue(all(reference() is None for reference in references))
            if before is not None:
                self.assertEqual(len(list(descriptor_path.iterdir())), before)
