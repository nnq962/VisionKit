"""Kiểm thử stride video, kết quả rỗng và huỷ subprocess stream."""

import asyncio
import tempfile
import unittest
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
