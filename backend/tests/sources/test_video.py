"""Kiểm thử API video bằng FFmpeg thật với database và storage tạm."""

import hashlib
import json
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
from app.storage.video_processing import inspect_video


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

    def mov_payload(self, *, hevc: bool = False) -> bytes:
        """Tạo MOV H.264 hoặc HEVC 10-bit để tái hiện lỗi codec trên trình duyệt."""
        root = self.settings.database_path.parent
        original = root / "input.mp4"
        original.write_bytes(self.payload)
        output = root / "phone.MOV"
        options = (
            [
                "-vf",
                "format=yuv420p10le",
                "-c:v",
                "libx265",
                "-x265-params",
                "pools=1:frame-threads=1",
                "-threads",
                "1",
            ]
            if hevc
            else ["-c", "copy"]
        )
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(original),
                *options,
                "-f",
                "mov",
                str(output),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return output.read_bytes()

    def assert_browser_video(self, payload: bytes) -> None:
        """Xác minh video trả về thực sự là MP4/H.264 8-bit và giải mã được."""
        output = self.settings.database_path.parent / "playback.mp4"
        output.write_bytes(payload)
        info = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name,pix_fmt",
                    "-of",
                    "json",
                    str(output),
                ],
                timeout=30,
            )
        )
        self.assertEqual(info["streams"][0]["codec_name"], "h264")
        self.assertEqual(info["streams"][0]["pix_fmt"], "yuv420p")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
            check=True,
            capture_output=True,
            timeout=30,
        )

    def test_mov_draft_preparation_preserves_library(self) -> None:
        """Chuẩn bị MOV HEVC 10-bit thành MP4; không giữ file tạm hoặc thêm source."""
        response = self.client.post(
            "/api/v1/sources/prepare-video",
            files={
                "file": ("phone.MOV", self.mov_payload(hevc=True), "video/quicktime")
            },
        )
        self.assertEqual(response.status_code, 200, response.text[:100])
        self.assertEqual(response.headers["content-type"], "video/mp4")
        self.assert_browser_video(response.content)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])
        self.assertEqual(self.client.get("/api/v1/sources").json()["total"], 0)

    def test_saved_mov_playback_preserves_original_and_cleans_sidecar(self) -> None:
        """MOV cũ có MP4 phát/tua được, tái dùng sidecar, xoá/rollback đủ các file."""
        payload = self.mov_payload()
        # Mô phỏng bản ghi MOV có từ trước khi upload được chuẩn hoá sang MP4.
        storage = self.app.state.sources.storage
        legacy = storage.path("legacy.mov")
        legacy.write_bytes(payload)
        metadata, thumbnail = inspect_video(legacy)
        storage.path("legacy.preview.jpg").write_bytes(thumbnail)
        metadata.update(
            preview_location="legacy.preview.jpg", preview_mime_type="image/jpeg"
        )
        source = self.app.state.sources.response(
            self.app.state.sources.repository.create(
                name="phone.MOV", kind="video", location=legacy.name, metadata=metadata
            )
        ).model_dump(mode="json")
        url = f"/api/v1/sources/{source['id']}"
        playback = self.client.get(f"{url}/playback")
        self.assertEqual(playback.status_code, 200)
        self.assert_browser_video(playback.content)
        self.assertEqual(self.client.get(source["content_url"]).content, payload)
        with patch(
            "app.storage.local.create_video_playback", side_effect=AssertionError
        ):
            partial = self.client.get(
                f"{url}/playback", headers={"Range": "bytes=0-99"}
            )
        self.assertEqual(partial.status_code, 206)
        self.assertEqual(partial.headers["content-type"], "video/mp4")
        self.assertEqual(partial.content, playback.content[:100])
        repository = self.app.state.sources.repository
        with patch.object(repository, "delete", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                self.client.delete(url)
        self.assertEqual(len(list(self.settings.sources_path.iterdir())), 3)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_mov_upload_stores_mp4_once_with_matching_metadata(self) -> None:
        """MOV upload chỉ chuyển mã một lần; lưu MP4 thật với metadata/hash khớp byte."""
        payload = self.mov_payload(hevc=True)
        from app.storage.local import create_video_playback

        with patch(
            "app.storage.local.create_video_playback", wraps=create_video_playback
        ) as convert:
            response = self.client.post(
                "/api/v1/sources/upload",
                files={"file": ("phone.MOV", payload, "video/quicktime")},
                data={"kind": "video"},
            )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(convert.call_count, 1)
        source = response.json()
        metadata = source["metadata"]
        self.assertTrue(source["location"].endswith(".mp4"))
        self.assertEqual(metadata["original_filename"], "phone.mp4")
        self.assertEqual(metadata["uploaded_filename"], "phone.MOV")
        self.assertEqual(metadata["format"], "MP4")
        self.assertEqual(metadata["mime_type"], "video/mp4")
        self.assertEqual(metadata["codec"], "h264")
        with patch(
            "app.storage.local.create_video_playback", side_effect=AssertionError
        ):
            stored = self.client.get(source["content_url"])
            for _ in range(2):
                playback = self.client.get(f"/api/v1/sources/{source['id']}/playback")
                self.assertEqual(playback.content, stored.content)
        self.assertEqual(metadata["size"], len(stored.content))
        self.assertEqual(metadata["sha256"], hashlib.sha256(stored.content).hexdigest())
        self.assert_browser_video(stored.content)
        self.assertEqual(len(list(self.settings.sources_path.iterdir())), 2)

    def test_mov_database_failure_removes_converted_files(self) -> None:
        """Ghi database lỗi phải dọn cả MP4 chuyển mã, thumbnail và upload tạm."""
        payload = self.mov_payload()
        with patch.object(
            self.app.state.sources.repository, "create", side_effect=RuntimeError
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    "/api/v1/sources/upload",
                    files={"file": ("phone.MOV", payload)},
                    data={"kind": "video"},
                )
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_preparation_failure_cleans_temporary_files(self) -> None:
        """Chuyển mã lỗi hoặc file hỏng phải dọn file và không ghi database."""
        with patch(
            "app.storage.video_processing.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 300),
        ):
            response = self.client.post(
                "/api/v1/sources/prepare-video",
                files={"file": ("phone.MOV", self.payload)},
            )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_mp4_playback_needs_no_conversion(self) -> None:
        """MP4/H.264 sẵn tương thích được trả nguyên byte, không tạo file thừa."""
        source = self.upload().json()
        with patch(
            "app.storage.local.create_video_playback", side_effect=AssertionError
        ):
            response = self.client.get(f"/api/v1/sources/{source['id']}/playback")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.payload)
        self.assertEqual(len(list(self.settings.sources_path.iterdir())), 2)
