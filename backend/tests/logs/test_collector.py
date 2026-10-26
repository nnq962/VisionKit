"""Kiểm tra thu log AI, phục hồi kết nối và hợp đồng HTTP cho web."""

import asyncio
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logs import LogBuffer
from app.main import create_app
from app.modules.logs.service import LogCollector
from app.modules.runs.service import RunService


# ------------------------- Kiểm thử bộ thu log AI ----------------------------
class CollectorTests(unittest.IsolatedAsyncioTestCase):
    """Giả lập API AI để kiểm tra cursor, chống trùng và trạng thái mất kết nối."""

    async def test_reconnect_restart_and_deduplication(self) -> None:
        """Lỗi mạng không xoá cursor; restart AI được phát hiện mà không nhân đôi log."""
        ai = LogBuffer("ai", capacity=2)
        run_id = str(uuid4())
        ai.append("INFO", "model ready", run_id=run_id)
        unavailable = False

        def respond(request: httpx.Request) -> httpx.Response:
            """Trả log từ AI giả lập hoặc mô phỏng kết nối bị từ chối."""
            if unavailable:
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(
                200, json=ai.read(request.url.params.get("after")).model_dump()
            )

        target = LogBuffer("backend")
        collector = LogCollector(target, "http://ai")
        await collector.client.aclose()
        collector.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            await collector.collect()
            await collector.collect()
            self.assertEqual(len(target.read(service="ai").items), 1)
            entry = target.read(service="ai").items[0]
            self.assertEqual(entry.run_id, run_id)
            self.assertEqual(entry.source_id, ai.read().items[0].id)
            self.assertEqual(entry.timestamp, ai.read().items[0].timestamp)
            cursor = collector.cursor
            unavailable = True
            await collector.collect()
            self.assertFalse(collector.status["available"])
            self.assertEqual(collector.cursor, cursor)
            unavailable = False
            for index in range(4):
                ai.append("INFO", f"next {index}")
            await collector.collect()
            self.assertEqual(collector.status["dropped_batches"], 1)
            ai = LogBuffer("ai")
            ai.append("INFO", "restarted")
            await collector.collect()
            self.assertTrue(collector.status["available"])
            self.assertEqual(collector.status["reset_count"], 1)
            self.assertEqual(target.read(service="ai").items[-1].message, "restarted")
        finally:
            await collector.close()

    async def test_error_traceback_is_preserved_for_frontend(self) -> None:
        """Backend giữ traceback và run_id AI khi frontend chỉ yêu cầu mức ERROR."""
        source = LogBuffer("ai")
        run_id = str(uuid4())
        source.append(
            "ERROR",
            "worker failed",
            run_id=run_id,
            trace="RuntimeError: api_key=hidden",
        )

        def respond(request: httpx.Request) -> httpx.Response:
            """Trả trang lỗi AI đã giới hạn và che credential."""
            return httpx.Response(200, json=source.read().model_dump())

        target = LogBuffer("backend")
        collector = LogCollector(target, "http://ai")
        await collector.client.aclose()
        collector.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            await collector.collect()
            page = target.read(service="ai", min_level="ERROR", run_id=run_id)
            self.assertEqual(len(page.items), 1)
            self.assertIn("RuntimeError", page.items[0].traceback)
            self.assertNotIn("hidden", page.items[0].traceback)
            self.assertEqual(page.items[0].source_id, source.read().items[0].id)
        finally:
            await collector.close()


# -------------------------- Kiểm thử API tập trung ---------------------------
class LogApiTests(unittest.TestCase):
    """API web đọc được log backend ngay cả khi không cấu hình AI."""

    def test_filters_validation_and_no_cache(self) -> None:
        """Lọc theo dịch vụ/lượt chạy hoạt động; cursor sai trả 422 và không cache."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(
                Settings(
                    database_path=root / "db.sqlite3",
                    sources_path=root / "sources",
                    ai_url=None,
                )
            )
            with TestClient(app) as client:
                run_id = str(uuid4())
                app.state.logs.append("ERROR", "failed", run_id=run_id)
                response = client.get(
                    "/api/v1/logs",
                    params={
                        "run_id": run_id,
                        "service": "backend",
                        "min_level": "ERROR",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.json()["items"][0]["message"], "failed")
                self.assertFalse(response.json()["ai"]["configured"])
                self.assertEqual(client.get("/api/v1/logs?after=bad").status_code, 422)
                self.assertEqual(client.get("/api/v1/logs?limit=501").status_code, 422)
                self.assertEqual(
                    client.get("/api/v1/logs?service=unknown").status_code, 422
                )
                self.assertEqual(client.get("/api/v1/logs?run_id=bad").status_code, 422)


# -------------------------- Kiểm thử dọn tài nguyên --------------------------
class LifespanCleanupTests(unittest.IsolatedAsyncioTestCase):
    """Xác minh startup/shutdown lỗi vẫn giải phóng các service đã khởi tạo."""

    async def test_partial_startup_and_shutdown_failure_close_resources(self) -> None:
        """Lỗi tạo RunService hoặc shutdown runs không bỏ quên model/collector/handler."""
        for stage in ("cleanup", "runs", "shutdown"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                app = create_app(
                    Settings(
                        database_path=root / "db.sqlite3", sources_path=root / "sources"
                    )
                )
                original = list(logging.getLogger("app").handlers)

                shutdown = RunService.shutdown

                async def fail(*args, **kwargs) -> None:
                    """Mô phỏng lỗi startup hoặc lỗi sau khi service runs đã dọn tài nguyên."""
                    if stage == "shutdown":
                        await shutdown(app.state.runs)
                    raise RuntimeError("simulated failure")

                target = {
                    "cleanup": "app.main.ModelService.cleanup_temporary",
                    "runs": "app.main.RunService",
                    "shutdown": "app.main.RunService.shutdown",
                }[stage]
                replacement = (
                    RuntimeError("simulated failure") if stage == "runs" else fail
                )
                before = asyncio.all_tasks()
                with (
                    patch(target, side_effect=replacement),
                    self.assertRaises(RuntimeError),
                ):
                    async with app.router.lifespan_context(app):
                        pass
                self.assertTrue(app.state.models.client.is_closed)
                self.assertTrue(app.state.log_collector.client.is_closed)
                if app.state.models.cleanup_task:
                    self.assertTrue(app.state.models.cleanup_task.done())
                self.assertEqual(logging.getLogger("app").handlers, original)
                self.assertFalse(
                    [task for task in asyncio.all_tasks() - before if not task.done()]
                )
