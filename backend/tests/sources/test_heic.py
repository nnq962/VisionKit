"""Kiểm tra ảnh HEIC/HEIF gốc, preview JPEG và vòng đời các file liên quan."""

import tempfile
import unittest
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app


# --------------------------- Tạo ảnh HEIC kiểm thử ---------------------------
def heic_bytes(orientation: int = 1) -> bytes:
    """Tạo HEIC thật 96×64, kèm EXIF orientation để kiểm tra giải mã và xoay ảnh."""
    image = Image.new("RGB", (96, 64), "red")
    exif = Image.Exif()
    exif[274] = orientation
    output = BytesIO()
    image.save(output, format="HEIF", exif=exif.tobytes())
    return output.getvalue()


# ---------------------------- Kiểm thử ảnh iPhone ----------------------------
class HeicApiTests(unittest.TestCase):
    """Dùng file HEIC thật để kiểm tra API, chỉ ghi dữ liệu vào thư mục tạm."""

    def setUp(self) -> None:
        """Tạo app với DB/storage tạm và tự đóng client/dọn file sau mỗi test."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.settings = Settings(
            database_path=root / "db.sqlite3", sources_path=root / "sources"
        )
        self.app = create_app(self.settings)
        self.client = stack.enter_context(TestClient(self.app))

    def test_inspect_rotated_heic_without_saving(self) -> None:
        """Preview áp dụng chiều xoay, không tạo bản ghi hoặc giữ file tạm."""
        response = self.client.post(
            "/api/v1/sources/inspect",
            files={"file": ("IMG_001.HEIC", heic_bytes(6), "image/heic")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.headers["x-image-width"], "64")
        self.assertEqual(response.headers["x-image-height"], "96")
        with Image.open(BytesIO(response.content)) as preview:
            self.assertEqual(preview.size, (64, 96))
            self.assertNotIn(preview.getexif().get(274), (6, 8))
        self.assertEqual(self.client.get("/api/v1/sources").json()["total"], 0)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_original_preview_persistence_and_deletion(self) -> None:
        """Giữ nguyên HEIF gốc, có JPEG preview và xoá cả hai sau khi mở lại app."""
        original = heic_bytes(8)
        response = self.client.post(
            "/api/v1/sources/upload",
            files={"file": ("IMG_002.heif", original, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        source = response.json()
        self.assertEqual(source["metadata"]["format"], "HEIC")
        self.assertEqual(
            (source["metadata"]["width"], source["metadata"]["height"]), (64, 96)
        )
        self.assertEqual(self.client.get(source["content_url"]).content, original)
        with TestClient(create_app(self.settings)) as client:
            preview = client.get(source["preview_url"])
            self.assertEqual(preview.headers["content-type"], "image/jpeg")
            with Image.open(BytesIO(preview.content)) as image:
                self.assertEqual(image.size, (64, 96))
            self.assertEqual(
                client.patch(
                    f"/api/v1/sources/{source['id']}", json={"name": "Ảnh iPhone"}
                ).status_code,
                200,
            )
            self.assertEqual(len(list(self.settings.sources_path.iterdir())), 2)
            self.assertEqual(
                client.delete(f"/api/v1/sources/{source['id']}").status_code, 204
            )
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_failed_database_operations_clean_or_restore_both_files(self) -> None:
        """Lỗi thêm DB dọn cả gốc/preview; lỗi xoá DB khôi phục đủ hai file."""
        repository = self.app.state.sources.repository
        original = heic_bytes()
        with (
            patch.object(
                repository, "create", side_effect=RuntimeError("DB unavailable")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.client.post(
                "/api/v1/sources/upload", files={"file": ("IMG.heic", original)}
            )
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])
        source = self.client.post(
            "/api/v1/sources/upload", files={"file": ("IMG.heic", original)}
        ).json()
        with (
            patch.object(
                repository, "delete", side_effect=RuntimeError("DB unavailable")
            ),
            self.assertRaises(RuntimeError),
        ):
            self.client.delete(f"/api/v1/sources/{source['id']}")
        self.assertEqual(self.client.get(source["content_url"]).content, original)
        self.assertEqual(self.client.get(source["preview_url"]).status_code, 200)
        self.assertEqual(len(list(self.settings.sources_path.iterdir())), 2)

    def test_invalid_heic_is_rejected_and_cleaned(self) -> None:
        """Tên HEIC không đủ: cả inspect/upload phải từ chối nội dung hỏng và dọn file."""
        for endpoint in ("inspect", "upload"):
            response = self.client.post(
                f"/api/v1/sources/{endpoint}",
                files={"file": ("bad.heic", b"not a HEIC image", "image/heic")},
            )
            self.assertEqual(response.status_code, 415)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_iphone_jpeg_exif_orientation(self) -> None:
        """Ảnh JPEG iPhone có EXIF orientation cũng được đọc đúng chiều khi preview."""
        image = Image.new("RGB", (96, 64), "blue")
        exif = Image.Exif()
        exif[274] = 6
        output = BytesIO()
        image.save(output, format="JPEG", exif=exif.tobytes())
        response = self.client.post(
            "/api/v1/sources/inspect", files={"file": ("IMG.jpg", output.getvalue())}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.headers["x-image-width"], response.headers["x-image-height"]),
            ("64", "96"),
        )
        with Image.open(BytesIO(response.content)) as preview:
            self.assertEqual(preview.size, (64, 96))
