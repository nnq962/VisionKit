"""Kiểm tra stderr thực, giới hạn dòng và context lượt chạy trên AI API."""

import asyncio
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.contracts.model import InspectRequest
from app.contracts.prediction import PredictRequest
from app.core.config import Settings
from app.core.logs import LogBuffer, attach_logging, detach_logging, run_context
from app.core.worker_logs import drain_stderr, read_worker_output, stop_worker
from app.inference.service import InferenceService
from app.inspection.service import InspectionService
from app.main import create_app


# --------------------------- Kiểm thử stderr worker --------------------------
class WorkerLogTests(unittest.IsolatedAsyncioTestCase):
    """Worker ghi nhiều stderr vẫn thoát; stdout JSON được giữ nguyên."""

    async def test_stderr_flood_is_drained_and_bounded(self) -> None:
        """Pipe không đầy gây deadlock, số dòng và kích thước log đều hữu hạn."""
        buffer = LogBuffer("ai")
        attached = attach_logging(buffer)
        token = run_context.set("test-run")
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "import sys; sys.stderr.write(('x'*10000+'\\n')*100); print('{\"ok\":true}')",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stderr_task = asyncio.create_task(drain_stderr(process.stderr))
            output, _ = await asyncio.wait_for(read_worker_output(process), 5)
            await asyncio.wait_for(stderr_task, 5)
            self.assertEqual(output.strip(), b'{"ok":true}')
            entries = buffer.read().items
            self.assertLessEqual(len(entries), 25)
            self.assertTrue(all(entry.run_id == "test-run" for entry in entries))
            self.assertTrue(all(len(entry.message) <= 8192 for entry in entries))
            self.assertTrue(any("lược bớt" in entry.message for entry in entries))
        finally:
            run_context.reset(token)
            detach_logging(attached)

    async def test_stdout_overflow_and_timeout_reap_worker(self) -> None:
        """Output quá lớn hoặc timeout phải dừng worker thật, không treo do pipe đầy."""
        for flood in (True, False):
            with self.subTest(flood=flood):
                code = (
                    "import sys,time; "
                    + (
                        "sys.stdout.write('x'*1000000); sys.stdout.flush(); "
                        if flood
                        else ""
                    )
                    + "time.sleep(30)"
                )
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-c",
                    code,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stderr_task = asyncio.create_task(drain_stderr(process.stderr))
                try:
                    with patch("app.core.worker_logs.MAX_WORKER_OUTPUT_BYTES", 1024):
                        with self.assertRaises(
                            ValueError if flood else asyncio.TimeoutError
                        ):
                            await asyncio.wait_for(
                                read_worker_output(process), 2 if flood else 0.1
                            )
                finally:
                    await asyncio.wait_for(stop_worker(process, stderr_task), 5)
                self.assertIsNotNone(process.returncode)
                self.assertTrue(stderr_task.done())

    async def test_structured_error_survives_stderr_flood_and_filter(self) -> None:
        """Lỗi ảnh/video/inspect giữ traceback đã che secret tại ERROR dù stderr bị lược bỏ."""
        buffer = LogBuffer("ai")
        attached = attach_logging(buffer)
        token = run_context.set(str(uuid4()))
        original_spawn = asyncio.create_subprocess_exec

        async def spawn(*args, **kwargs):
            """Thay model bằng worker thật phát lỗi có cấu trúc sau một đợt stderr lớn."""
            output = {
                "type": "error",
                "error": "worker failed",
                "status": "failed",
                "message": "worker failed",
                "traceback": "RuntimeError: api_key=hidden",
            }
            code = (
                "import sys; sys.stderr.write('noise\\n'*1000); print("
                + repr(json.dumps(output))
                + ")"
            )
            return await original_spawn(sys.executable, "-c", code, **kwargs)

        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "model.pt").write_bytes(b"fixture")
                (root / "source.png").write_bytes(b"fixture")
                (root / "source.mp4").write_bytes(b"fixture")
                request = PredictRequest(
                    model_location="model.pt",
                    model_sha256="0" * 64,
                    source_location="source.png",
                    source_sha256="0" * 64,
                )
                service = InferenceService(Settings(models_path=root, runs_path=root))
                with patch("asyncio.create_subprocess_exec", side_effect=spawn):
                    with self.assertRaisesRegex(ValueError, "worker failed"):
                        await service.predict(request)
                    events = [
                        event
                        async for event in service.video(
                            request.model_copy(update={"source_location": "source.mp4"})
                        )
                    ]
                    self.assertNotIn("traceback", events[0])
                    result = await InspectionService(
                        Settings(models_path=root)
                    ).inspect(InspectRequest(location="model.pt", sha256="0" * 64))
                    self.assertEqual(result.status, "failed")
            errors = buffer.read(min_level="ERROR").items
            self.assertEqual(len(errors), 3)
            for entry in errors:
                self.assertEqual(entry.run_id, run_context.get())
                self.assertIn("RuntimeError", entry.traceback)
                self.assertNotIn("hidden", entry.traceback)
        finally:
            run_context.reset(token)
            detach_logging(attached)

    async def test_real_inspection_worker_returns_error_traceback(self) -> None:
        """Worker metadata thật trả traceback ERROR thay vì chỉ có các dòng stderr INFO."""
        buffer = LogBuffer("ai")
        attached = attach_logging(buffer)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "bad.pt").write_bytes(b"invalid model")
                result = await InspectionService(Settings(models_path=root)).inspect(
                    InspectRequest(
                        location="bad.pt",
                        sha256=hashlib.sha256(b"invalid model").hexdigest(),
                    )
                )
                self.assertEqual(result.status, "failed")
            errors = buffer.read(min_level="ERROR").items
            self.assertEqual(len(errors), 1)
            self.assertIn("Traceback", errors[0].traceback)
        finally:
            detach_logging(attached)


# ----------------------------- Kiểm thử API AI -------------------------------
class AiLogApiTests(unittest.TestCase):
    """Log API không tự ghi thêm request và header run ID được kiểm tra."""

    def test_log_poll_is_quiet_and_bad_header_returns_422(self) -> None:
        """Poll lặp lại không phình buffer; log request lỗi vẫn lọc được theo UUID."""
        app = create_app()
        with TestClient(app) as client:
            page = client.get("/api/v1/logs").json()
            next_page = client.get(
                "/api/v1/logs", params={"after": page["next_cursor"]}
            )
            self.assertEqual(next_page.json()["items"], [])
            self.assertEqual(next_page.headers["cache-control"], "no-store")
            self.assertEqual(client.get("/api/v1/logs?after=bad").status_code, 422)
            self.assertEqual(
                client.get(
                    "/api/v1/health", headers={"X-VisionKit-Run-ID": "bad"}
                ).status_code,
                422,
            )
            run_id = str(uuid4())
            client.post(
                "/api/v1/inference/image",
                json={},
                headers={"X-VisionKit-Run-ID": run_id},
            )
            items = client.get("/api/v1/logs", params={"run_id": run_id}).json()[
                "items"
            ]
            self.assertTrue(items)
            self.assertTrue(all(entry["run_id"] == run_id for entry in items))
