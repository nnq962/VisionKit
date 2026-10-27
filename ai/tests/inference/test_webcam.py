"""Kiểm webcam local tái dùng live worker, preview và hợp đồng index thiết bị."""

import base64
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np
from pydantic import ValidationError

from app.adapters.ultralytics.stream import predict_stream, webcam_preview
from app.contracts.prediction import WebcamCheckRequest, WebcamPredictRequest
from app.media_sources.exceptions import StreamError
from app.media_sources.readers.webcam import WebcamReader
from tests.inference import test_stream as fixtures


# ------------------------- Kiểm webcam và preview local -----------------------
class WebcamTests(unittest.TestCase):
    """Không mở camera thật trong test; webcam phải đọc integer và không nhận URL."""

    def test_contract_rejects_remote_sources_and_invalid_indices(self) -> None:
        """ID âm/bool/string và URL đều bị từ chối trước khi mở camera."""
        for value in [-1, 16, True, "0", "rtsp://camera"]:
            with self.assertRaises(ValidationError):
                WebcamCheckRequest(device_index=value)
        with self.assertRaises(ValidationError):
            WebcamCheckRequest(stream_url="rtsp://camera")
        self.assertEqual(WebcamCheckRequest().device_index, 0)

    def test_adapter_reads_device_once_and_produces_jpeg_from_same_frame(self) -> None:
        """Factory nhận số 0, model nạp một lần, JPEG không nằm trong result JSON."""
        request = WebcamPredictRequest.model_validate(
            {
                **fixtures.request_fixture(options={"vid_stride": 3}).model_dump(
                    exclude={"stream_url"}
                ),
                "device_index": 0,
            }
        )
        batch = fixtures.FakeBatch()
        model = fixtures.CheckingModel()
        events = []
        with (
            patch(
                "app.adapters.ultralytics.stream.load_model",
                return_value=(model, "cpu"),
            ) as load,
            patch("app.adapters.ultralytics.stream.create_media_source") as create,
            patch(
                "app.adapters.ultralytics.stream.StreamBatchReader", return_value=batch
            ),
            patch(
                "app.adapters.ultralytics.stream.time.perf_counter",
                side_effect=[index / 100 for index in range(1, 15)] + [1.1],
            ),
            patch("app.adapters.ultralytics.stream.time.sleep"),
        ):
            predict_stream(Path("model.pt"), request, events.append)
        create.assert_called_once_with(0, warmup_seconds=1)
        load.assert_called_once()
        self.assertEqual(events[-1]["reason"], "duration_limit")
        self.assertTrue(batch.closed)
        jpeg = cv2.imdecode(
            np.frombuffer(base64.b64decode(events[0]["preview_jpeg"]), dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        self.assertEqual(jpeg.shape[:2], (32, 32))
        self.assertNotIn("preview_jpeg", events[0]["result"])

    def test_preview_is_bounded(self) -> None:
        """Frame lớn chỉ nén preview tối đa 960px; không thay đổi ndarray dùng suy luận."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        jpeg = cv2.imdecode(
            np.frombuffer(base64.b64decode(webcam_preview(frame)), dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        self.assertEqual(jpeg.shape[:2], (540, 960))
        self.assertEqual(frame.shape, (1080, 1920, 3))


# ---------------------------- Ổn định ảnh webcam -----------------------------
class WebcamWarmupTests(unittest.TestCase):
    """Camera bỏ frame đen lúc vừa mở nhưng vẫn giải phóng đúng khi khởi động lỗi."""

    def test_warmup_discards_startup_frames_before_snapshot(self) -> None:
        """Sáu frame đầu chưa sáng không được dùng làm ảnh kiểm tra."""
        cap = Mock()
        cap.isOpened.return_value = True
        cap.get.return_value = 30
        black = np.zeros((8, 8, 3), dtype=np.uint8)
        bright = np.full((8, 8, 3), 128, dtype=np.uint8)
        cap.read.side_effect = [(True, black)] * 6 + [(True, bright)]
        with (
            patch(
                "app.media_sources.readers.webcam.cv2.VideoCapture", return_value=cap
            ),
            patch(
                "app.media_sources.readers.webcam.time.monotonic", side_effect=[0, 1]
            ),
        ):
            with WebcamReader(0, warmup_seconds=1) as reader:
                frame, _ = reader.read()
                self.assertEqual(float(frame.mean()), 128)
        self.assertEqual(cap.read.call_count, 7)
        cap.release.assert_called_once()

    def test_failed_warmup_releases_camera(self) -> None:
        """Khởi động không có frame luôn đóng capture, không giữ webcam bận."""
        cap = Mock()
        cap.isOpened.return_value = True
        cap.read.return_value = (False, None)
        with patch(
            "app.media_sources.readers.webcam.cv2.VideoCapture", return_value=cap
        ):
            with self.assertRaises(StreamError):
                WebcamReader(0, warmup_seconds=1).open()
        cap.release.assert_called_once()
