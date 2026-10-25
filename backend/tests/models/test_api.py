"""Kiểm thử tải model với mạng giả lập, DB và thư mục tạm; không tải weights thật."""

import hashlib
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import anyio
import httpx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.models.catalog.ultralytics import VARIANTS

PAYLOAD = b"model-test-data" * 50000
ORIGINAL_CLIENT = httpx.AsyncClient


# --------------------------- Luồng dữ liệu kiểm thử ---------------------------
class SlowStream(httpx.AsyncByteStream):
    """Phát chunks có độ trễ để kiểm tra tiến độ và huỷ trước khi tải hoàn tất."""

    def __init__(self, content: bytes, delay: float = 0.02) -> None:
        """Giữ content và số giây chờ delay giữa các chunks; không mở tài nguyên."""
        self.content = content
        self.delay = delay

    async def __aiter__(self):
        """Phát từng khối 64 KiB sau một nhịp chờ; cho phép cancel task khi tải."""
        for start in range(0, len(self.content), 65536):
            await anyio.sleep(self.delay)
            yield self.content[start : start + 65536]

    async def aclose(self) -> None:
        """Đáp ứng giao diện stream HTTPX; không có file/socket riêng cần đóng."""


# ---------------------------- Kiểm thử API model -----------------------------
class ModelApiTests(unittest.TestCase):
    """Xác minh download thật theo byte, persistence và rollback mà không cần PyTorch."""

    def setUp(self) -> None:
        """Khởi tạo app và HTTP client giả lập; mọi dữ liệu được tự dọn cuối mỗi test."""
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.settings = Settings(
            database_path=root / "db.sqlite3",
            sources_path=root / "sources",
            models_path=root / "models",
            model_download_concurrency=1,
        )
        self.variant = VARIANTS["yolo11n.pt"].model_copy(
            update={
                "expected_bytes": len(PAYLOAD),
                "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
            }
        )
        self.second = VARIANTS["yolo26n.pt"].model_copy(
            update={
                "expected_bytes": len(PAYLOAD),
                "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
            }
        )
        self.stack.enter_context(
            patch.dict(
                VARIANTS, {self.variant.id: self.variant, self.second.id: self.second}
            )
        )
        self.mode = "valid"
        self.delay = 0.02
        self.stack.enter_context(
            patch(
                "app.modules.models.service.httpx.AsyncClient",
                side_effect=self.make_client,
            )
        )
        self.application = create_app(self.settings)
        self.client = self.stack.enter_context(TestClient(self.application))

    def make_client(self, **kwargs) -> httpx.AsyncClient:
        """Tạo client với MockTransport thay cho mạng; giữ cùng interface của service."""
        return ORIGINAL_CLIENT(transport=httpx.MockTransport(self.handle), **kwargs)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """Trả luồng đúng, sai checksum/size hoặc lỗi HTTP theo mode của test."""
        if self.mode == "network":
            return httpx.Response(503)
        content = PAYLOAD if self.mode != "checksum" else b"x" * len(PAYLOAD)
        if self.mode == "truncated":
            content = content[:100]
        return httpx.Response(200, stream=SlowStream(content, self.delay))

    def start(self, catalog_id: str = "yolo11n.pt") -> dict:
        """POST catalog_id và yêu cầu 202, trả JSON job để theo dõi kết quả."""
        response = self.client.post(
            "/api/v1/models/downloads", json={"catalog_id": catalog_id}
        )
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def wait(self, job_id: str) -> tuple[dict, list[int]]:
        """Poll tối đa 5 giây, trả job cuối và các giá trị tiến độ đã quan sát."""
        progress = []
        for _ in range(250):
            job = self.client.get(f"/api/v1/models/downloads/{job_id}").json()
            progress.append(job["progress"])
            if job["status"] not in ("queued", "downloading"):
                return job, progress
            time.sleep(0.02)
        self.fail("Download không kết thúc đúng hạn")

    def test_download_progress_duplicate_persistence_delete(self) -> None:
        """Tải đúng checksum, chống trùng, theo dõi progress, mở lại app và xoá weights."""
        self.delay = 0.06
        job = self.start()
        duplicate = self.start()
        self.assertEqual(job["id"], duplicate["id"])
        final, progress = self.wait(job["id"])
        self.assertEqual(final["status"], "completed", final)
        self.assertTrue(any(0 < value < 100 for value in progress), progress)
        self.assertEqual(final["downloaded_bytes"], len(PAYLOAD))
        model = self.client.get("/api/v1/models").json()["items"][0]
        path = self.settings.models_path / model["location"]
        self.assertEqual(path.read_bytes(), PAYLOAD)
        self.assertEqual(model["sha256"], hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(
            self.client.post(
                "/api/v1/models/downloads", json={"catalog_id": self.variant.id}
            ).status_code,
            409,
        )
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(len(reopened.get("/api/v1/models").json()["items"]), 1)
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{model['id']}").status_code, 204
        )
        self.assertFalse(path.exists())

    def test_catalog_and_validation(self) -> None:
        """Catalog có size/checksum; từ chối URL tuỳ ý, ID giả và giới hạn model."""
        catalog = self.client.get("/api/v1/models/catalog").json()
        self.assertEqual(len(catalog["families"]), 5)
        self.assertTrue(all(len(item["sha256"]) == 64 for item in catalog["variants"]))
        self.assertEqual(
            self.client.post(
                "/api/v1/models/downloads", json={"catalog_id": "../../bad"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/models/downloads",
                json={"catalog_id": self.variant.id, "url": "http://localhost/secret"},
            ).status_code,
            422,
        )
        self.application.state.models.files.max_bytes = 10
        self.assertEqual(
            self.client.post(
                "/api/v1/models/downloads", json={"catalog_id": self.variant.id}
            ).status_code,
            413,
        )

    def test_failures_and_retry(self) -> None:
        """Mạng lỗi, file thiếu hoặc checksum sai không tạo model/file; cho thử lại."""
        for mode in ("network", "checksum", "truncated"):
            with self.subTest(mode=mode):
                self.mode = mode
                final, _ = self.wait(self.start()["id"])
                self.assertEqual(final["status"], "failed")
                self.assertTrue(final["error"])
                self.assertEqual(self.client.get("/api/v1/models").json()["items"], [])
                self.assertEqual(list(self.settings.models_path.iterdir()), [])
        self.mode = "valid"
        final, _ = self.wait(self.start()["id"])
        self.assertEqual(final["status"], "completed")

    def test_cancel_running_and_queued(self) -> None:
        """Huỷ lượt đang tải và queued, dọn file tạm và không ghi vào thư viện."""
        self.delay = 0.2
        first, second = self.start(), self.start(self.second.id)
        for job in (second, first):
            result = self.client.delete(f"/api/v1/models/downloads/{job['id']}")
            self.assertEqual(result.json()["status"], "cancelled", result.text)
        self.assertEqual(self.client.get("/api/v1/models").json()["items"], [])
        self.assertEqual(list(self.settings.models_path.iterdir()), [])

    def test_database_failures_roll_back_files(self) -> None:
        """Lỗi commit dọn file weights; lỗi xoá DB khôi phục file để không mất model."""
        repository = self.application.state.models.repository
        with patch.object(
            repository, "complete", side_effect=RuntimeError("database failed")
        ):
            final, _ = self.wait(self.start()["id"])
        self.assertEqual(final["status"], "failed")
        self.assertEqual(list(self.settings.models_path.iterdir()), [])
        self.wait(self.start()["id"])
        model = repository.models()[0]
        with patch.object(
            repository, "delete", side_effect=RuntimeError("database failed")
        ):
            with self.assertRaises(RuntimeError):
                self.client.delete(f"/api/v1/models/{model.id}")
        self.assertEqual(
            (self.settings.models_path / model.location).read_bytes(), PAYLOAD
        )
        self.assertFalse(list(self.settings.models_path.glob("*.trash")))

    def test_restart_marks_interrupted_jobs(self) -> None:
        """Khởi động lại đánh dấu job cũ failed và dọn .part, giữ model đã hoàn tất."""
        repository = self.application.state.models.repository
        job = repository.create_job(self.variant)
        temporary = self.settings.models_path / f"{job.id}.part"
        temporary.write_bytes(b"partial")
        with TestClient(create_app(self.settings)) as reopened:
            result = reopened.get(f"/api/v1/models/downloads/{job.id}").json()
            self.assertEqual(result["status"], "failed")
            self.assertIn("gián đoạn", result["error"])
        self.assertFalse(temporary.exists())

    def test_shutdown_interrupts_active_download(self) -> None:
        """Dừng service khi đang tải phải đánh dấu failed và dọn phần file chưa hoàn tất."""
        self.delay = 0.2
        job = self.start()
        time.sleep(0.05)
        self.client.portal.call(self.application.state.models.shutdown)
        result = self.client.get(f"/api/v1/models/downloads/{job['id']}").json()
        self.assertEqual(result["status"], "failed")
        self.assertIn("gián đoạn", result["error"])
        self.assertEqual(list(self.settings.models_path.iterdir()), [])
