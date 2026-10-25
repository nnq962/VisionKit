"""Kiểm thử lưu model riêng, metadata khai báo và kiểm tra file trước khi chọn."""

import hashlib
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from httpx import Response

from app.core.config import Settings
from app.main import create_app


# --------------------------- Kiểm thử upload model ---------------------------
class ModelUploadTests(unittest.TestCase):
    """Kiểm tra storage/API độc lập AI bằng nội dung nhị phân, không load weights."""

    def setUp(self) -> None:
        """Tạo DB và storage tạm, mở TestClient và tự đóng tài nguyên sau test."""
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.settings = Settings(
            database_path=root / "db.sqlite3",
            sources_path=root / "sources",
            models_path=root / "models",
        )
        self.app = create_app(self.settings)
        self.client = self.stack.enter_context(TestClient(self.app))
        self.payload = b"binary-content-is-stored-without-loading-a-runtime" * 20

    def upload(self, filename: str = "custom.pt", **fields: str) -> Response:
        """Gửi file nhị phân và trường form cho API upload model, trả HTTP response."""
        return self.client.post(
            "/api/v1/models/upload",
            files={"file": (filename, self.payload, "application/octet-stream")},
            data=fields,
        )

    def test_upload_select_and_reopen(self) -> None:
        """Upload PT, trả UUID và checksum, đọc lại chi tiết/DB sau khi mở lại app."""
        response = self.upload(
            name="  Model cổng chính  ", family="yolo", task="detect"
        )
        self.assertEqual(response.status_code, 201, response.text)
        model = response.json()
        UUID(model["id"])
        self.assertEqual(model["variant"]["name"], "Model cổng chính")
        self.assertEqual(model["variant"]["origin"], "upload")
        self.assertEqual(model["variant"]["format"], "pt")
        self.assertIsNone(model["variant"]["size"])
        self.assertEqual(model["size_bytes"], len(self.payload))
        self.assertEqual(model["sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(
            (self.settings.models_path / model["location"]).read_bytes(), self.payload
        )
        self.assertEqual(
            self.client.get(f"/api/v1/models/{model['id']}").status_code, 200
        )
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get("/api/v1/models").json()["items"][0]["id"], model["id"]
            )
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{model['id']}").status_code, 204
        )
        self.assertEqual(list(self.settings.models_path.iterdir()), [])

    def test_onnx_yoloe_and_safe_names(self) -> None:
        """Lưu ONNX của YOLOE với task segment; tên file gốc không điều khiển đường dẫn."""
        response = self.upload("../../my-model.ONNX", family="yoloe", task="segment")
        self.assertEqual(response.status_code, 201, response.text)
        model = response.json()
        self.assertEqual(model["variant"]["filename"], "my-model.ONNX")
        self.assertEqual(model["variant"]["familyName"], "YOLOE")
        self.assertEqual(model["variant"]["task"], "segment")
        self.assertTrue(model["location"].endswith(".onnx"))
        self.assertNotIn("/", model["location"])

    def test_invalid_uploads_leave_no_files(self) -> None:
        """Từ chối sai đuôi, file rỗng, tên/họ/tác vụ sai và quá dung lượng."""
        self.assertEqual(self.upload("model.exe").status_code, 415)
        self.assertEqual(self.upload(name=" ").status_code, 422)
        self.assertEqual(self.upload(name="x" * 121).status_code, 422)
        self.assertEqual(self.upload(family="retinaface").status_code, 422)
        self.assertEqual(self.upload(task="wrong").status_code, 422)
        self.assertEqual(self.upload(family="yoloe", task="detect").status_code, 422)
        self.assertEqual(
            self.client.post(
                "/api/v1/models/upload", files={"file": ("empty.pt", b"")}
            ).status_code,
            422,
        )
        with TestClient(
            create_app(replace(self.settings, max_model_upload_bytes=10))
        ) as client:
            response = client.post(
                "/api/v1/models/upload", files={"file": ("large.pt", self.payload)}
            )
            self.assertEqual(response.status_code, 413)
        self.assertEqual(list(self.settings.models_path.iterdir()), [])
        self.assertEqual(self.client.get("/api/v1/models").json()["items"], [])

    def test_database_error_cleans_new_file(self) -> None:
        """Lỗi ghi metadata rollback file mới; không tạo model nửa chừng trong DB."""
        with patch.object(
            self.app.state.models.repository,
            "create_uploaded",
            side_effect=RuntimeError("write failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertEqual(list(self.settings.models_path.iterdir()), [])
        self.assertEqual(self.client.get("/api/v1/models").json()["items"], [])

    def test_missing_or_modified_model_cannot_be_selected(self) -> None:
        """GET model từ chối file mất hoặc đổi dung lượng để pipeline không dùng ID hỏng."""
        model = self.upload().json()
        path = self.settings.models_path / model["location"]
        path.write_bytes(b"changed")
        self.assertEqual(
            self.client.get(f"/api/v1/models/{model['id']}").status_code, 409
        )
        path.unlink()
        self.assertEqual(
            self.client.get(f"/api/v1/models/{model['id']}").status_code, 404
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{model['id']}").status_code, 204
        )

    def test_upload_same_filename_keeps_distinct_models(self) -> None:
        """Hai tệp trùng tên có UUID/file riêng, không ghi đè weights đã lưu."""
        first, second = self.upload().json(), self.upload().json()
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(first["location"], second["location"])
        self.assertEqual(len(self.client.get("/api/v1/models").json()["items"]), 2)
