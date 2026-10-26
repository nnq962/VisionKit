"""Kiểm thử vòng đời model tạm, gia hạn và lưu vào thư viện."""

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.models.schemas import InspectionMetadata, ModelInspection


# ---------------------------- Kiểm thử model tạm -----------------------------
class TemporaryModelTests(unittest.TestCase):
    """Dùng DB/file thật trong thư mục riêng, không chạm model người dùng hoặc chạy AI."""

    def setUp(self) -> None:
        """Tạo app, storage và client tạm; tự đóng và dọn tài nguyên sau mỗi test."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.settings = Settings(
            database_path=root / "db.sqlite3",
            sources_path=root / "sources",
            models_path=root / "models",
        )
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.service = self.app.state.models

    def upload(self) -> dict:
        """Upload file tạm, xác minh 201 và trả bản ghi có thời hạn dùng."""
        response = self.client.post(
            "/api/v1/models/temporary", files={"file": ("best.pt", b"fixture")}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def expire(self, model_id: str) -> None:
        """Đặt hạn dùng quá khứ trong DB riêng để kiểm tra cleanup ngay, không phải đợi 24 giờ."""
        with self.service.repository.database.connection() as connection:
            connection.execute(
                "UPDATE models SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",
                (model_id,),
            )

    def test_inspect_before_save_and_promote_without_reupload(self) -> None:
        """Model tạm đọc được metadata, không ở thư viện; lưu giữ nguyên ID/file/checksum/metadata."""
        model = self.upload()
        self.assertIsNotNone(model["expires_at"])
        self.assertEqual(self.client.get("/api/v1/models").json()["items"], [])
        self.service.repository.set_inspection(
            model["id"],
            ModelInspection(
                status="ready",
                metadata=InspectionMetadata(
                    format="pt", family="yolo", task="detect", class_count=2
                ),
            ),
        )
        detail = self.client.get(f"/api/v1/models/{model['id']}").json()
        self.assertEqual(detail["inspection"]["metadata"]["class_count"], 2)
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get(f"/api/v1/models/{model['id']}").json()["inspection"][
                    "status"
                ],
                "ready",
            )
            self.assertEqual(reopened.get("/api/v1/models").json()["items"], [])
        url = f"/api/v1/models/{model['id']}/save"
        saved = self.client.post(url, json={"name": " Model riêng "}).json()
        self.assertIsNone(saved["expires_at"])
        for key in ("id", "location", "sha256"):
            self.assertEqual(saved[key], model[key])
        self.assertEqual(saved["inspection"]["status"], "ready")
        self.assertEqual(saved["variant"]["name"], "Model riêng")
        self.assertEqual(
            self.client.post(url, json={"name": "Model riêng"}).status_code, 200
        )
        self.client.portal.call(self.service.cleanup_temporary)
        self.assertEqual(len(self.client.get("/api/v1/models").json()["items"]), 1)
        self.assertEqual(len(list(self.settings.models_path.iterdir())), 1)

    def test_expiry_cleanup_and_renewal(self) -> None:
        """Truy cập gia hạn model tạm; file hết hạn bị từ chối và dọn, file thư viện vẫn còn."""
        model = self.upload()
        before = self.service.repository.model(model["id"]).expires_at
        self.client.get(f"/api/v1/models/{model['id']}")
        self.assertGreater(
            self.service.repository.model(model["id"]).expires_at, before
        )
        saved = self.client.post(
            "/api/v1/models/upload", files={"file": ("saved.pt", b"weights")}
        ).json()
        self.expire(model["id"])
        self.assertEqual(
            self.client.get(f"/api/v1/models/{model['id']}").status_code, 410
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/models/{model['id']}/save", json={"name": "expired"}
            ).status_code,
            410,
        )
        self.client.portal.call(self.service.cleanup_temporary)
        self.assertIsNone(self.service.repository.model(model["id"]))
        self.assertFalse((self.settings.models_path / model["location"]).exists())
        self.assertEqual(
            self.client.get(f"/api/v1/models/{saved['id']}").status_code, 200
        )

    def test_invalid_upload_or_save_preserves_state(self) -> None:
        """File sai bị từ chối; lưu tên rỗng giữ nguyên model tạm, không thêm vào thư viện."""
        for filename, payload, status in [
            ("model.exe", b"a", 415),
            ("empty.pt", b"", 422),
        ]:
            self.assertEqual(
                self.client.post(
                    "/api/v1/models/temporary", files={"file": (filename, payload)}
                ).status_code,
                status,
            )
        model = self.upload()
        self.assertEqual(
            self.client.post(
                f"/api/v1/models/{model['id']}/save", json={"name": " "}
            ).status_code,
            422,
        )
        self.assertIsNotNone(self.service.repository.model(model["id"]).expires_at)
        self.assertEqual(self.client.get("/api/v1/models").json()["items"], [])

    def test_startup_cleanup_keeps_active_temporary(self) -> None:
        """Backend khởi động dọn model hết hạn nhưng giữ model tạm còn hạn."""
        expired, active = self.upload(), self.upload()
        self.expire(expired["id"])
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get(f"/api/v1/models/{expired['id']}").status_code, 404
            )
            self.assertEqual(
                reopened.get(f"/api/v1/models/{active['id']}").status_code, 200
            )
        self.assertFalse((self.settings.models_path / expired["location"]).exists())
