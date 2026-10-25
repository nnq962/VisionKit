"""Kiểm thử API video bằng FFmpeg thật với database và storage tạm."""

import shutil
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from httpx import Response

from app.core.config import Settings
from app.main import create_app


# ---------------------------- Kiểm thử API video -----------------------------
@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Cần FFmpeg")
class VideoApiTests(unittest.TestCase):
    """Xác minh metadata, range request, thumbnail và rollback video thật."""

    def setUp(self) -> None:
        """Tạo video MP4 một giây và app trong thư mục tạm, tự dọn sau mỗi test."""
        stack = ExitStack()
        self.addCleanup(stack.close)
        root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        video = root / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=160x90:r=25",
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(video),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        self.payload = video.read_bytes()
        self.settings = Settings(
            database_path=root / "db.sqlite3", sources_path=root / "sources"
        )
        self.app = create_app(self.settings)
        self.client = stack.enter_context(TestClient(self.app))

    def upload(self) -> Response:
        """Gửi MP4 với MIME giả để kiểm tra API xác minh theo nội dung thật."""
        return self.client.post(
            "/api/v1/sources/upload",
            files={"file": ("../../clip.mp4", self.payload, "text/plain")},
            data={"kind": "video", "name": "Video thử"},
        )

    def test_lifecycle_and_range(self) -> None:
        """Kiểm tra metadata, thumbnail JPEG, tua theo byte, mở lại app, đổi tên và xoá."""
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.text)
        source = response.json()
        self.assertEqual(source["metadata"]["width"], 160)
        self.assertEqual(source["metadata"]["height"], 90)
        self.assertEqual(source["metadata"]["fps"], 25)
        self.assertAlmostEqual(source["metadata"]["duration"], 1, places=1)
        self.assertEqual(source["metadata"]["codec"], "h264")
        self.assertEqual(self.client.get(source["content_url"]).content, self.payload)
        partial = self.client.get(
            source["content_url"], headers={"Range": "bytes=0-99"}
        )
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.content, self.payload[:100])
        self.assertEqual(partial.headers["content-type"], "video/mp4")
        preview = self.client.get(source["preview_url"])
        self.assertEqual(preview.headers["content-type"], "image/jpeg")
        self.assertTrue(preview.content.startswith(b"\xff\xd8"))
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get("/api/v1/sources?kind=video").json()["total"], 1
            )
        url = f"/api/v1/sources/{source['id']}"
        self.assertEqual(
            self.client.patch(url, json={"name": "Tên mới"}).json()["name"], "Tên mới"
        )
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_invalid_limit_and_missing_tools(self) -> None:
        """Từ chối file giả/quá lớn/thiếu FFmpeg, không để lại file hoặc bản ghi."""
        invalid = self.client.post(
            "/api/v1/sources/upload",
            files={"file": ("bad.mp4", b"invalid", "video/mp4")},
            data={"kind": "video"},
        )
        self.assertEqual(invalid.status_code, 415)
        with TestClient(
            create_app(replace(self.settings, max_video_upload_bytes=10))
        ) as client:
            result = client.post(
                "/api/v1/sources/upload",
                files={"file": ("clip.mp4", self.payload)},
                data={"kind": "video"},
            )
            self.assertEqual(result.status_code, 413)
        with patch(
            "app.storage.video_processing.subprocess.run", side_effect=FileNotFoundError
        ):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])
        self.assertEqual(self.client.get("/api/v1/sources").json()["total"], 0)

    def test_database_rollback(self) -> None:
        """Lỗi tạo DB dọn cả video/thumbnail; lỗi xoá khôi phục đủ hai file."""
        repository = self.app.state.sources.repository
        with patch.object(repository, "create", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                self.upload()
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])
        source = self.upload().json()
        with patch.object(repository, "delete", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                self.client.delete(f"/api/v1/sources/{source['id']}")
        self.assertEqual(self.client.get(source["content_url"]).status_code, 200)
        self.assertEqual(self.client.get(source["preview_url"]).status_code, 200)
        self.assertEqual(len(list(self.settings.sources_path.iterdir())), 2)
