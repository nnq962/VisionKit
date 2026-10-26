"""Kiểm thử hợp đồng RTSP, worker/process thật và adapter không dùng mạng ngoài."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.adapters.ultralytics.stream import predict_stream
from app.contracts.prediction import StreamPredictRequest
from app.core.config import Settings
from app.inference.service import InferenceService
from app.main import create_app
from app.media_sources import SourceMeta, SourceType
from tests.sources.test_integration import CheckingModel


# ----------------------------- Dữ liệu RTSP thử ------------------------------
def request_fixture(**updates: object) -> StreamPredictRequest:
    """Tạo cấu hình nội bộ có URL bí mật; không thực hiện kết nối."""
    return StreamPredictRequest(
        model_location="model.pt",
        model_sha256="0" * 64,
        stream_url="rtsp://operator:very-private@127.0.0.1:8554/live?token=also-private",
        duration_seconds=1,
        **updates,
    )


# --------------------------- Kiểm thử hợp đồng -------------------------------
class StreamContractTests(unittest.TestCase):
    """Chỉ cho phép RTSP/RTSPS, validation không phản chiếu credential."""

    def test_serialization_masks_url_except_worker_stdin(self) -> None:
        """URL thật chỉ xuất hiện trong worker_payload dành cho stdin, không repr/JSON công khai."""
        request = request_fixture()
        self.assertNotIn("very-private", repr(request))
        self.assertNotIn("very-private", request.model_dump_json())
        payload = json.loads(request.worker_payload())
        self.assertEqual(payload["stream_url"], request.stream_url.get_secret_value())
        self.assertNotIn("source_location", payload)
        self.assertNotIn("source_sha256", payload)

    def test_rejects_other_protocols_and_duration(self) -> None:
        """Không cho mở HTTP/file/camera khác qua endpoint RTSP hoặc chạy vô hạn."""
        for url in [
            "http://cam/live",
            "file:///private",
            "rtmp://cam/live",
            "rtsp://cam:bad/live",
            "rtsp:///live",
        ]:
            payload = json.loads(request_fixture().worker_payload())
            payload["stream_url"] = url
            with self.assertRaises(ValidationError):
                StreamPredictRequest.model_validate(payload)
        for duration in [0, 14401, True, 1.5]:
            payload = json.loads(request_fixture().worker_payload())
            payload["duration_seconds"] = duration
            with self.assertRaises(ValidationError):
                StreamPredictRequest.model_validate(payload)

    def test_api_validation_does_not_echo_url(self) -> None:
        """Lỗi Pydantic trong FastAPI nội bộ không chứa raw body camera."""
        with TestClient(create_app()) as client:
            payload = json.loads(request_fixture().worker_payload())
            payload["duration_seconds"] = 0
            response = client.post("/api/v1/inference/stream", json=payload)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("very-private", response.text)
            response = client.post(
                "/api/v1/inference/stream", json={**payload, "source_location": "x"}
            )
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("also-private", response.text)


# ------------------------------ Batch kiểm thử -------------------------------
class FakeBatch:
    """Batch trả các frame chỉ định; dùng clock ngoài để kiểm duration và cleanup."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Tạo frame đỏ BGR và index không liên tục như latest-frame thực tế."""
        self.closed = False
        self.indices = iter([1, 2, 7])

    def __enter__(self) -> "FakeBatch":
        """Trả batch đã sẵn sàng, không mở camera."""
        return self

    def __exit__(self, *args: object) -> None:
        """Đánh dấu dọn nguồn khi adapter hoàn tất hoặc lỗi."""
        self.closed = True

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        """Trả frame đỏ cùng metadata live và thời điểm thu nhận."""
        index = next(self.indices)
        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        frame[:, :, 2] = 255
        return [frame], [
            SourceMeta(
                "camera",
                SourceType.RTSP,
                index,
                (32, 32),
                fps=24,
                is_stream=True,
                timestamp=100 + index / 24,
            )
        ]


# --------------------------- Kiểm thử adapter RTSP ---------------------------
class StreamAdapterTests(unittest.TestCase):
    """Live stride theo khoảng cách index mới nhất, không phụ thuộc index chia hết."""

    def test_live_stride_duration_and_cleanup(self) -> None:
        """Index 1/7 vẫn suy luận với stride 3; completed có reason duration_limit."""
        batch = FakeBatch()
        model = CheckingModel()
        request = request_fixture(options={"vid_stride": 3})
        events = []
        # Clock tăng đều; sleep chỉ được ghi nhận để test không chờ thời gian thật.
        clock = [index / 100 for index in range(1, 15)] + [1.1]
        with (
            patch(
                "app.adapters.ultralytics.stream.load_model",
                return_value=(model, "cpu"),
            ),
            patch("app.adapters.ultralytics.stream.create_media_source"),
            patch(
                "app.adapters.ultralytics.stream.StreamBatchReader", return_value=batch
            ),
            patch(
                "app.adapters.ultralytics.stream.time.perf_counter", side_effect=clock
            ),
            patch("app.adapters.ultralytics.stream.time.time", return_value=100),
            patch("app.adapters.ultralytics.stream.time.sleep") as sleep,
        ):
            predict_stream(Path("model.pt"), request, events.append)
        self.assertEqual([e["result"]["frameId"] for e in events], [1, 7, 7])
        self.assertEqual(events[-1]["type"], "completed")
        self.assertEqual(events[-1]["reason"], "duration_limit")
        self.assertIsNone(events[-1]["progress"]["total_frames"])
        self.assertIsNone(events[-1]["progress"]["percent"])
        self.assertEqual(len(model.shapes), 2)
        self.assertTrue(sleep.called)
        self.assertTrue(batch.closed)

    def test_fps_cap_waits_before_reading_latest_slot(self) -> None:
        """Hai frame mỗi giây, chỉ đọc slot sau khi chờ và không suy luận quá hạn."""
        batch = FakeBatch()
        batch.indices = iter(range(100))
        clock = [0.0]
        waits = []
        events = []

        def sleep(seconds: float) -> None:
            """Tiến clock giả thay vì chờ thực để kiểm nhịp suy luận."""
            waits.append(seconds)
            clock[0] += seconds

        with (
            patch(
                "app.adapters.ultralytics.stream.load_model",
                return_value=(CheckingModel(), "cpu"),
            ),
            patch("app.adapters.ultralytics.stream.create_media_source"),
            patch(
                "app.adapters.ultralytics.stream.StreamBatchReader", return_value=batch
            ),
            patch(
                "app.adapters.ultralytics.stream.time.perf_counter",
                side_effect=lambda: clock[0],
            ),
            patch("app.adapters.ultralytics.stream.time.sleep", side_effect=sleep),
        ):
            predict_stream(
                Path("model.pt"), request_fixture(options={"max_fps": 2}), events.append
            )
        self.assertEqual([event["result"]["frameId"] for event in events], [0, 1, 1])
        self.assertEqual(waits, [0.5, 0.5])
        self.assertTrue(batch.closed)

    def test_publish_failure_closes_source(self) -> None:
        """Ngắt consumer khi nhận frame sẽ giải phóng batch qua context manager."""
        batch = FakeBatch()

        def fail(event: dict) -> None:
            """Giả lập lỗi ghi stdout khi phía backend đã dừng nhận."""
            raise RuntimeError("consumer")

        with (
            patch(
                "app.adapters.ultralytics.stream.load_model",
                return_value=(CheckingModel(), "cpu"),
            ),
            patch("app.adapters.ultralytics.stream.create_media_source"),
            patch(
                "app.adapters.ultralytics.stream.StreamBatchReader", return_value=batch
            ),
        ):
            with self.assertRaises(RuntimeError):
                predict_stream(Path("model.pt"), request_fixture(), fail)
        self.assertTrue(batch.closed)


# --------------------------- Kiểm thử child thật -----------------------------
class StreamWorkerTests(unittest.IsolatedAsyncioTestCase):
    """Pipe/process thực để xác minh stdin bí mật, huỷ, EOF lỗi và thu hồi semaphore."""

    async def test_cancel_reaps_worker_and_never_puts_url_in_arguments(self) -> None:
        """Đóng generator sau frame đầu phải kill/reap child và release semaphore."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "model.pt").write_bytes(b"fixture")
            service = InferenceService(Settings(models_path=root))
            original = asyncio.create_subprocess_exec
            children = []

            async def spawn(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
                """Giữ pipe thật, chỉ thay code worker không cần camera/model."""
                self.assertIn("app.inference.stream_worker", args)
                self.assertNotIn("very-private", " ".join(args))
                child = await original(
                    args[0],
                    "-c",
                    'import sys,json,time; p=json.loads(sys.stdin.read()); assert "very-private" in p["stream_url"]; print(json.dumps({"type":"frame"}),flush=True); time.sleep(60)',
                    **kwargs,
                )
                children.append(child)
                return child

            with patch(
                "app.inference.service.asyncio.create_subprocess_exec",
                side_effect=spawn,
            ):
                generator = service.stream(request_fixture())
                self.assertEqual((await anext(generator))["type"], "frame")
                await generator.aclose()
            self.assertIsNotNone(children[0].returncode)
            self.assertFalse(service.semaphore.locked())

    async def test_worker_eof_is_error_and_reaps_process(self) -> None:
        """Worker đóng stdout trước terminal không được báo completed hoặc giữ lease."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "model.pt").write_bytes(b"fixture")
            service = InferenceService(Settings(models_path=root))
            original = asyncio.create_subprocess_exec
            children = []

            async def spawn(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
                """Child đọc stdin rồi thoát code 0 nhưng không gửi terminal."""
                child = await original(
                    args[0], "-c", "import sys;sys.stdin.read()", **kwargs
                )
                children.append(child)
                return child

            with patch(
                "app.inference.service.asyncio.create_subprocess_exec",
                side_effect=spawn,
            ):
                with self.assertRaises(ValueError):
                    async for _ in service.stream(request_fixture()):
                        pass
            self.assertIsNotNone(children[0].returncode)
            self.assertFalse(service.semaphore.locked())

    async def test_model_path_validation_precedes_network(self) -> None:
        """Không tạo worker với path thoát storage; không mở mạng nếu model sai."""
        with tempfile.TemporaryDirectory() as temporary:
            service = InferenceService(Settings(models_path=Path(temporary)))
            request = request_fixture().model_copy(
                update={"model_location": "../outside.pt"}
            )
            with patch("app.inference.service.asyncio.create_subprocess_exec") as spawn:
                with self.assertRaises(ValueError):
                    async for _ in service.stream(request):
                        pass
                spawn.assert_not_called()


# ----------------------- Kiểm thử entrypoint thực ----------------------------
class StreamEntrypointTests(unittest.TestCase):
    """Entrypoint thực không lộ URL/checksum lỗi ra stdout/stderr."""

    def test_bad_checksum_returns_sanitized_error(self) -> None:
        """Model sai checksum bị từ chối trước nạp model/kết nối camera."""
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "model.pt"
            model.write_bytes(b"fixture")
            result = subprocess.run(
                [sys.executable, "-m", "app.inference.stream_worker", str(model)],
                input=request_fixture().worker_payload(),
                capture_output=True,
                timeout=20,
                env={**os.environ, "YOLO_AUTOINSTALL": "false"},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            event = json.loads(result.stdout)
            self.assertEqual(event["type"], "error")
            self.assertNotIn(b"very-private", result.stdout + result.stderr)
            self.assertNotIn(b"also-private", result.stdout + result.stderr)
