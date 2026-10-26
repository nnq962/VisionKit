"""Kiểm thử reader trong adapter Ultralytics và giải phóng khi model/consumer lỗi."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import torch
from PIL import Image
from ultralytics.engine.results import Results

from app.adapters.ultralytics.video import predict_video
from app.adapters.ultralytics.yolo import predict_image
from app.contracts.options import PredictOptions
from app.contracts.prediction import PredictRequest
from app.media_sources.readers.video import VideoReader


# --------------------------- Model kiểm tra màu ------------------------------
class CheckingModel:
    """Model fixture xác minh adapter đưa BGR ndarray thay vì ảnh PIL/RGB."""

    def __init__(self) -> None:
        """Giữ shape và lần gọi để kiểm tra contract."""
        self.shapes = []

    def predict(self, source: np.ndarray, **kwargs: object) -> list[Results]:
        """Kiểm tra màu đỏ BGR và trả Results thật không có detection."""
        assert isinstance(source, np.ndarray)
        assert source.dtype == np.uint8
        assert source[0, 0, 2] > 240 and source[0, 0, 0] < 15
        self.shapes.append(source.shape)
        return [
            Results(
                source, path="fixture", names={0: "person"}, boxes=torch.empty((0, 6))
            )
        ]


# ------------------------- Kiểm thử tích hợp reader --------------------------
class AdapterReaderTests(unittest.TestCase):
    """Giữ hợp đồng JSON/timeline cũ trong lúc chuyển decoder sang media_sources."""

    def test_image_orientation_bgr_and_result_contract(self) -> None:
        """Adapter dùng reader mới; màu/hướng và toạ độ ảnh gốc không đổi."""
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "fixture.jpg"
            exif = Image.Exif()
            exif[274] = 6
            Image.new("RGB", (24, 12), "red").save(image, exif=exif)
            model = CheckingModel()
            request = PredictRequest(
                model_location="model.pt",
                model_sha256="0" * 64,
                source_location=image.name,
                source_sha256="0" * 64,
            )
            with patch(
                "app.adapters.ultralytics.yolo.load_model", return_value=(model, "cpu")
            ) as loader:
                result = predict_image(Path("model.pt"), image, request)
            self.assertEqual(model.shapes, [(24, 12, 3)])
            loader.assert_called_once()
            self.assertEqual(result["sourceSize"], {"width": 12, "height": 24})
            self.assertEqual(result["detections"], [])
            self.assertEqual(result["device"], "cpu")
            self.assertGreaterEqual(result["elapsedMs"], 0)

    def test_video_closes_on_prediction_or_publish_failure_and_keeps_pacing(
        self,
    ) -> None:
        """Lỗi model/consumer không rò capture; pacing frame cuối vẫn chờ timeline thật."""
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / "fixture.mp4"
            writer = cv2.VideoWriter(
                str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10, (32, 32)
            )
            self.assertTrue(writer.isOpened())
            frame = np.zeros((32, 32, 3), dtype=np.uint8)
            frame[:, :, 2] = 255
            for _ in range(3):
                writer.write(frame)
            writer.release()
            request = PredictRequest(
                model_location="model.pt",
                model_sha256="0" * 64,
                source_location=video.name,
                source_sha256="0" * 64,
                options=PredictOptions(vid_stride=2),
            )
            original_close = VideoReader.close
            closed = []

            def close(reader: VideoReader) -> None:
                """Ghi nhận capture được trả lại, vẫn đóng capture thật."""
                original_close(reader)
                closed.append(reader._cap)

            for failure in ["model", "publish"]:
                model = CheckingModel()

                def publish(event: dict) -> None:
                    """Giả lập consumer dừng nhận khi đang xử lý frame."""
                    raise RuntimeError("publish failed")

                if failure == "model":
                    model.predict = lambda **kwargs: (_ for _ in ()).throw(
                        RuntimeError("model failed")
                    )
                with (
                    patch(
                        "app.adapters.ultralytics.video.load_model",
                        return_value=(model, "cpu"),
                    ),
                    patch.object(VideoReader, "close", close),
                ):
                    with self.assertRaises(RuntimeError):
                        predict_video(Path("model.pt"), video, request, publish)
                self.assertIsNone(closed[-1])
            events = []
            with (
                patch(
                    "app.adapters.ultralytics.video.load_model",
                    return_value=(CheckingModel(), "cpu"),
                ),
                patch(
                    "app.adapters.ultralytics.video.time.perf_counter", return_value=10
                ),
                patch("app.adapters.ultralytics.video.time.sleep") as sleep,
            ):
                predict_video(Path("model.pt"), video, request, events.append)
            self.assertEqual(
                [event["result"]["frameId"] for event in events], [0, 2, 2]
            )
            self.assertAlmostEqual(sleep.call_args.args[0], 0.2, places=3)
            self.assertEqual(events[-1]["type"], "completed")
            self.assertEqual(events[-1]["progress"]["percent"], 100)
