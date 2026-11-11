"""Kiểm thử stride video, kết quả rỗng và huỷ subprocess stream."""

import asyncio
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from unittest.mock import patch

import cv2
import numpy as np
import torch
from ultralytics.engine.results import Results

from app.adapters.ultralytics.video import predict_video
from app.contracts.options import PredictOptions
from app.contracts.prediction import PredictRequest
from app.core.config import Settings
from app.inference.service import InferenceService
from app.media_sources.models import SourceMeta, SourceType


# ------------------------------ Model giả lập --------------------------------
class FakeModel:
    """Trả Results thật theo ảnh đầu vào, đánh dấu một frame không có đối tượng."""

    def __init__(self) -> None:
        """Khởi tạo bộ đếm để kiểm tra stride và số lần predict."""
        self.calls = 0

    def predict(self, source: np.ndarray, **kwargs: Any) -> list[Results]:
        """Trả frame thứ hai rỗng để kiểm tra client phải xoá bbox cũ."""
        self.calls += 1
        boxes = (
            torch.empty((0, 6))
            if self.calls == 2
            else torch.tensor([[1, 2, 10, 12, 0.9, 0]])
        )
        return [Results(source, path="frame", names={0: "person"}, boxes=boxes)]


# ----------------------------- Kiểm thử video --------------------------------
class VideoPredictionTests(unittest.TestCase):
    """Đọc MP4 thật nhưng thay model để kiểm tra contract nhanh, không tải weights."""

    def test_stride_frame_ids_and_empty_result(self) -> None:
        """Stride 2 xử lý frame 0/2/4 và vẫn gửi frame rỗng, terminal đánh dấu 100%."""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "clip.mp4"
            writer = cv2.VideoWriter(
                str(path), cv2.VideoWriter_fourcc(*"mp4v"), 100, (32, 32)
            )
            self.assertTrue(writer.isOpened())
            for _ in range(6):
                writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
            writer.release()
            events = []
            fake = FakeModel()
            request = PredictRequest(
                model_location="model.pt",
                model_sha256="0" * 64,
                source_location=path.name,
                source_sha256="0" * 64,
                options=PredictOptions(vid_stride=2),
            )
            with patch(
                "app.adapters.ultralytics.video.load_model", return_value=(fake, "cpu")
            ) as loader:
                predict_video(Path("model.pt"), path, request, events.append)
            self.assertEqual(loader.call_count, 1)
            self.assertEqual(fake.calls, 3)
            self.assertEqual(
                [event["result"]["frameId"] for event in events[:-1]], [0, 2, 4]
            )
            self.assertEqual(events[1]["result"]["detections"], [])
            self.assertEqual(events[-1]["type"], "completed")
            self.assertEqual(events[-1]["progress"]["percent"], 100)
            self.assertEqual(events[-1]["progress"]["frames_processed"], 3)

    def test_slow_model_skips_backlog_without_warmup_drift(self) -> None:
        """Model 35 FPS bỏ frame trễ của video 60 FPS; model nhanh vẫn xử lý đủ frame."""
        image = np.zeros((32, 32, 3), dtype=np.uint8)
        frames = [
            (
                image,
                SourceMeta(
                    "clip.mp4",
                    SourceType.VIDEO,
                    index,
                    (32, 32),
                    fps=60,
                    total_frames=120,
                    timestamp_ms=index / 60 * 1000,
                ),
            )
            for index in range(120)
        ]
        for prediction_seconds in (1 / 35, 0.002):
            with self.subTest(prediction_seconds=prediction_seconds):
                clock = [0.0]
                fake = FakeModel()
                predict = fake.predict
                events = []
                emitted = []

                def slow_predict(**kwargs: Any) -> list[Results]:
                    """Mô phỏng warmup dài một lần và thời gian suy luận mỗi frame."""
                    clock[0] += 0.75 if fake.calls == 0 else prediction_seconds
                    return predict(**kwargs)

                def sleep(seconds: float) -> None:
                    """Tiến đồng hồ ảo để kiểm tra pacing mà không chờ thực tế."""
                    self.assertGreaterEqual(seconds, 0)
                    clock[0] += seconds

                def publish(event: dict) -> None:
                    """Ghi thời gian gửi frame để đo độ trễ so với đồng hồ preview."""
                    events.append(event)
                    if event["type"] == "frame":
                        emitted.append((clock[0], event["result"]["timestampMs"]))

                request = PredictRequest(
                    model_location="model.pt",
                    model_sha256="0" * 64,
                    source_location="clip.mp4",
                    source_sha256="0" * 64,
                    family="yoloe",
                    options=PredictOptions(vid_stride=1),
                )
                with (
                    patch(
                        "app.adapters.ultralytics.video.load_model",
                        return_value=(fake, "cpu"),
                    ),
                    patch(
                        "app.adapters.ultralytics.video.create_media_source",
                        return_value=nullcontext(iter(frames)),
                    ),
                    patch(
                        "app.adapters.ultralytics.video.time.perf_counter",
                        side_effect=lambda: clock[0],
                    ),
                    patch(
                        "app.adapters.ultralytics.video.time.sleep", side_effect=sleep
                    ),
                    patch.object(fake, "predict", side_effect=slow_predict),
                ):
                    predict_video(Path("model.pt"), Path("clip.mp4"), request, publish)
                origin = emitted[0][0]
                for wall_time, timestamp in emitted:
                    self.assertLess((wall_time - origin) * 1000 - timestamp, 50)
                self.assertEqual(events[1]["result"]["frameId"], 1)
                if prediction_seconds > 1 / 60:
                    self.assertGreater(fake.calls, 50)
                    self.assertLess(fake.calls, 100)
                else:
                    self.assertEqual(fake.calls, 120)
                self.assertEqual(events[-1]["progress"]["frames_processed"], fake.calls)
                self.assertEqual(events[-1]["progress"]["percent"], 100)


# --------------------------- Kiểm thử huỷ stream -----------------------------
class VideoWorkerTests(unittest.IsolatedAsyncioTestCase):
    """Chạy child thật nhưng payload giả lập để xác minh generator close kill child."""

    async def test_closing_stream_kills_worker(self) -> None:
        """Huỷ sau một event phải dừng process đang chờ và nhả semaphore cho lượt sau."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model.pt"
            model.write_bytes(b"fixture")
            video = root / "video.mp4"
            video.write_bytes(b"fixture")
            service = InferenceService(Settings(models_path=root, runs_path=root))
            request = PredictRequest(
                model_location=model.name,
                model_sha256="0" * 64,
                source_location=video.name,
                source_sha256="0" * 64,
            )
            original = asyncio.create_subprocess_exec
            children = []

            async def create(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
                """Thay worker bằng child xuất một event rồi chờ, vẫn dùng pipe thật."""
                child = await original(
                    args[0],
                    "-c",
                    'import sys,time;sys.stdin.read();print(\'{"type":"frame"}\',flush=True);time.sleep(60)',
                    **kwargs,
                )
                children.append(child)
                return child

            with patch(
                "app.inference.service.asyncio.create_subprocess_exec",
                side_effect=create,
            ):
                generator = service.video(request)
                self.assertEqual((await anext(generator))["type"], "frame")
                await generator.aclose()
            self.assertIsNotNone(children[0].returncode)
            self.assertFalse(service.semaphore.locked())
