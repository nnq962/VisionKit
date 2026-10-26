"""Kiểm thử kết nối backend tới AI qua HTTP, trạng thái và cập nhật metadata trong DB."""

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

ORIGINAL_CLIENT = httpx.AsyncClient


# ---------------------------- Kiểm thử cầu nối AI ----------------------------
class ModelInspectionTests(unittest.TestCase):
    """Dùng AI HTTP giả lập để xác minh pipeline backend mà không cài torch trong backend."""

    def setUp(self) -> None:
        """Tạo app/storage tạm và client AI giả lập, dọn tài nguyên sau mỗi test."""
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.settings = Settings(
            database_path=root / "db.sqlite3",
            sources_path=root / "sources",
            models_path=root / "models",
            ai_url="http://ai.test",
        )
        self.mode = "ready"
        self.delay = 0.02
        self.requests = []
        self.stack.enter_context(
            patch(
                "app.modules.models.service.httpx.AsyncClient",
                side_effect=self.make_client,
            )
        )
        self.app = create_app(self.settings)
        self.client = self.stack.enter_context(TestClient(self.app))

    def make_client(self, **kwargs) -> httpx.AsyncClient:
        """Tạo HTTPX client giữ API thật nhưng thay transport để không gọi dịch vụ bên ngoài."""
        return ORIGINAL_CLIENT(transport=httpx.MockTransport(self.handle), **kwargs)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """Trả kết quả AI theo mode, mô phỏng độ trễ để quan sát trạng thái đang đọc."""
        self.requests.append(request)
        await anyio.sleep(self.delay)
        if self.mode == "offline":
            raise httpx.ConnectError("offline", request=request)
        if self.mode == "failed":
            return httpx.Response(
                200, json={"status": "failed", "message": "File không đọc được."}
            )
        return httpx.Response(
            200,
            json={
                "status": self.mode,
                "message": None,
                "metadata": {
                    "format": "pt",
                    "family": "yolo" if self.mode == "ready" else None,
                    "task": "segment" if self.mode == "ready" else None,
                    "names": {"0": "person", "1": "car"},
                    "class_count": 2,
                    "imgsz": [640, 640],
                    "stride": 32,
                },
            },
        )

    def upload(self) -> dict:
        """Upload file không khai báo họ/tác vụ, trả model đã lưu để theo dõi inspect."""
        response = self.client.post(
            "/api/v1/models/upload",
            files={"file": ("best.pt", b"fixture data")},
            data={"name": "Model riêng"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def wait(self, model_id: str) -> dict:
        """Poll tối đa 3 giây đến khi lượt inspect kết thúc, trả model cập nhật."""
        for _ in range(150):
            model = self.client.get(f"/api/v1/models/{model_id}").json()
            if model["inspection"]["status"] not in {"queued", "processing"}:
                return model
            time.sleep(0.02)
        self.fail("Inspect chưa kết thúc")

    def test_auto_inspection_and_persistence(self) -> None:
        """Upload tự gọi AI, cập nhật task/family/classes và giữ kết quả khi mở lại DB."""
        model = self.wait(self.upload()["id"])
        self.assertEqual(model["inspection"]["status"], "ready")
        self.assertEqual(model["variant"]["task"], "segment")
        self.assertEqual(model["variant"]["familyName"], "YOLO")
        self.assertEqual(model["inspection"]["metadata"]["names"]["1"], "car")
        self.assertEqual(self.requests[0].url.path, "/api/v1/models/inspect")
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get(f"/api/v1/models/{model['id']}").json()["inspection"][
                    "status"
                ],
                "ready",
            )

    def test_ai_offline_preserves_model_and_retries(self) -> None:
        """AI offline không làm mất upload; thử đọc lại sau khi AI trở về hoạt động."""
        self.mode = "offline"
        model = self.wait(self.upload()["id"])
        self.assertEqual(model["inspection"]["status"], "unavailable")
        self.assertTrue((self.settings.models_path / model["location"]).is_file())
        self.mode = "ready"
        self.assertEqual(
            self.client.post(f"/api/v1/models/{model['id']}/inspect").status_code, 202
        )
        self.assertEqual(self.wait(model["id"])["inspection"]["status"], "ready")

    def test_partial_metadata_and_manual_fallback(self) -> None:
        """AI thiếu thông tin trả needs_input; khai báo thủ công được ghi nhãn manual."""
        self.mode = "needs_input"
        model = self.wait(self.upload()["id"])
        self.assertIsNone(model["variant"]["task"])
        response = self.client.patch(
            f"/api/v1/models/{model['id']}/metadata",
            json={"family": "yoloe", "task": "segment"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["inspection"]["status"], "manual")
        self.assertEqual(response.json()["variant"]["familyName"], "YOLOE")

    def test_failed_file_not_manually_approved(self) -> None:
        """File không đọc được giữ failed và không thể đổi nhãn thành hợp lệ bằng khai báo."""
        self.mode = "failed"
        model = self.wait(self.upload()["id"])
        self.assertEqual(model["inspection"]["status"], "failed")
        self.assertEqual(
            self.client.patch(
                f"/api/v1/models/{model['id']}/metadata",
                json={"family": "yolo", "task": "detect"},
            ).status_code,
            409,
        )

    def test_delete_during_inspection(self) -> None:
        """Xoá model khi AI còn đọc phải huỷ task và không tạo lại bản ghi từ kết quả muộn."""
        self.delay = 0.5
        model = self.upload()
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{model['id']}").status_code, 204
        )
        self.assertEqual(self.client.get("/api/v1/models").json()["items"], [])
