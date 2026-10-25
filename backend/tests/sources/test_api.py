"""Kiểm tra API ảnh với database và storage tạm, không chạm dữ liệu thật."""

import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from httpx import Response
from PIL import Image

from app.core.config import Settings
from app.main import create_app


# ----------------------------- Tạo ảnh kiểm thử ------------------------------
def image_bytes() -> bytes:
    """Tạo ảnh PNG RGB 64×32 trong bộ nhớ để thử upload và xác minh metadata."""
    output = BytesIO()
    Image.new("RGB", (64, 32), "blue").save(output, format="PNG")
    return output.getvalue()


# ---------------------------- Kiểm thử API source ----------------------------
class SourceApiTests(unittest.TestCase):
    """Kiểm tra vòng đời source, giới hạn upload và nhất quán file với SQLite."""

    def setUp(self) -> None:
        """Tạo ứng dụng và thư mục tạm; đăng ký tự đóng client và dọn file sau test."""
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.settings = Settings(
            database_path=root / "db.sqlite3", sources_path=root / "sources"
        )
        self.application = create_app(self.settings)
        self.client = self.stack.enter_context(TestClient(self.application))

    def upload(self, name: str = "Ảnh thử", kind: str = "image") -> Response:
        """Gửi PNG hợp lệ và trả response để test tên, loại và nội dung source."""
        return self.client.post(
            "/api/v1/sources/upload",
            files={"file": ("test.png", image_bytes(), "image/png")},
            data={"name": name, "kind": kind},
        )

    def test_complete_image_lifecycle(self) -> None:
        """Upload, preview, lọc, đổi tên và xoá cả bản ghi lẫn file thật."""
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        source = response.json()
        self.assertEqual(source["metadata"]["width"], 64)
        self.assertEqual(source["metadata"]["height"], 32)
        self.assertEqual(source["metadata"]["size"], len(image_bytes()))
        path = self.settings.sources_path / source["location"]
        self.assertTrue(path.is_file())
        content = self.client.get(source["content_url"])
        self.assertEqual(content.headers["content-type"], "image/png")
        self.assertEqual(content.content, image_bytes())
        self.assertEqual(
            self.client.get(f"/api/v1/sources/{source['id']}").json()["id"],
            source["id"],
        )
        page = self.client.get("/api/v1/sources?kind=image&limit=1").json()
        self.assertEqual(page["total"], 1)
        self.assertEqual(len(page["items"]), 1)
        renamed = self.client.patch(
            f"/api/v1/sources/{source['id']}", json={"name": "  Tên mới  "}
        )
        self.assertEqual(renamed.json()["name"], "Tên mới")
        self.assertEqual(
            self.client.delete(f"/api/v1/sources/{source['id']}").status_code, 204
        )
        self.assertFalse(path.exists())
        self.assertEqual(self.client.get(source["content_url"]).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/sources").json()["total"], 0)

    def test_persistence_and_screenshot(self) -> None:
        """Ảnh màn hình vẫn tồn tại khi tạo lại app với cùng DB/storage."""
        source = self.upload(kind="screen").json()
        with TestClient(create_app(self.settings)) as reopened:
            record = reopened.get(f"/api/v1/sources/{source['id']}").json()
            self.assertEqual(record["kind"], "screen")
            self.assertEqual(reopened.get(record["content_url"]).content, image_bytes())

    def test_invalid_input_and_safe_filename(self) -> None:
        """Từ chối file giả, tên rỗng và trường lạ; tên upload không điều khiển đường dẫn."""
        fake = self.client.post(
            "/api/v1/sources/upload",
            files={"file": ("fake.png", b"not an image", "image/png")},
        )
        self.assertEqual(fake.status_code, 415)
        self.assertEqual(self.upload(name=" ").status_code, 422)
        self.assertEqual(self.upload(kind="video").status_code, 415)
        result = self.client.post(
            "/api/v1/sources/upload",
            files={"file": ("../../pretend.exe", image_bytes(), "text/plain")},
        )
        self.assertEqual(result.status_code, 201)
        source = result.json()
        self.assertNotIn("/", source["location"])
        self.assertTrue(source["location"].endswith(".png"))
        self.assertEqual(source["metadata"]["mime_type"], "image/png")
        url = f"/api/v1/sources/{source['id']}"
        self.assertEqual(
            self.client.patch(
                url, json={"name": " ", "location": "/tmp/file"}
            ).status_code,
            422,
        )
        self.assertEqual(self.client.patch(url, json={"name": " "}).status_code, 422)
        self.assertFalse(list(self.settings.sources_path.glob("*.part")))

    def test_limit_and_missing_sources(self) -> None:
        """Kiểm tra giới hạn byte, pixel, phân trang và các ID không tồn tại."""
        for config in (
            replace(self.settings, max_upload_bytes=10),
            replace(self.settings, max_image_pixels=1),
        ):
            with TestClient(create_app(config)) as client:
                response = client.post(
                    "/api/v1/sources/upload",
                    files={"file": ("test.png", image_bytes(), "image/png")},
                )
                self.assertEqual(response.status_code, 413)
        missing = f"/api/v1/sources/{uuid4()}"
        self.assertEqual(self.client.get(missing).status_code, 404)
        self.assertEqual(self.client.delete(missing).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/sources?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/v1/sources?offset=-1").status_code, 422)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_failed_database_operations_preserve_consistency(self) -> None:
        """Lỗi ghi DB dọn file mới; lỗi xoá DB khôi phục file và giữ bản ghi."""
        repository = self.application.state.sources.repository
        with patch.object(
            repository, "create", side_effect=RuntimeError("write failed")
        ):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])
        source = self.upload().json()
        with patch.object(
            repository, "delete", side_effect=RuntimeError("delete failed")
        ):
            with self.assertRaises(RuntimeError):
                self.client.delete(f"/api/v1/sources/{source['id']}")
        self.assertEqual(self.client.get(source["content_url"]).status_code, 200)
        self.assertIsNotNone(repository.get(source["id"]))
        self.assertFalse(list(self.settings.sources_path.glob("*.trash")))

    def test_missing_file_and_path_escape(self) -> None:
        """Không đọc file ngoài storage; vẫn xoá được metadata của ảnh đã mất file."""
        source = self.upload().json()
        (self.settings.sources_path / source["location"]).unlink()
        self.assertEqual(self.client.get(source["content_url"]).status_code, 404)
        self.assertEqual(
            self.client.delete(f"/api/v1/sources/{source['id']}").status_code, 204
        )
        repository = self.application.state.sources.repository
        external = repository.create(
            name="Outside", kind="image", location="../../outside.png"
        )
        self.assertEqual(
            self.client.get(f"/api/v1/sources/{external.id}/content").status_code, 404
        )

    def test_health_and_cors(self) -> None:
        """Health trả trạng thái sẵn sàng; CORS cho phép origin web được cấu hình."""
        self.assertEqual(self.client.get("/api/v1/health").json(), {"status": "ok"})
        response = self.client.options(
            "/api/v1/sources/upload",
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(
            response.headers["access-control-allow-origin"], "http://localhost:3001"
        )

    def test_search_unicode_and_pagination(self) -> None:
        """Tìm tên Unicode trên toàn bộ DB, kết hợp lọc/phân trang và ký tự SQL literal."""
        self.upload(name="ẢNH Cổng chính", kind="image")
        self.upload(name="Ảnh sân", kind="screen")
        self.upload(name="100%_done", kind="image")
        page = self.client.get(
            "/api/v1/sources", params={"q": "ảnh", "limit": 1, "offset": 1}
        ).json()
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(
            self.client.get(
                "/api/v1/sources", params={"q": "ảnh", "kind": "screen"}
            ).json()["total"],
            1,
        )
        self.assertEqual(
            self.client.get("/api/v1/sources", params={"q": "%_"}).json()["total"], 1
        )
        self.assertEqual(
            self.client.get("/api/v1/sources", params={"q": "' OR 1=1 --"}).json()[
                "total"
            ],
            0,
        )
