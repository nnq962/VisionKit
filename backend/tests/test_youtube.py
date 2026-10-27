"""Kiểm job YouTube bằng process/file thật, không tải mạng trong unit test."""

import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import Settings
from app.core.errors import SourceError
from app.modules.youtube.service import YoutubeService
from tests.runs import test_api as fixtures

SPAWN = asyncio.create_subprocess_exec


# ------------------------- Kiểm vòng đời cache YouTube ------------------------
class YoutubeServiceTests(unittest.IsolatedAsyncioTestCase):
    """Giả resolver bằng child Python thật để kiểm cancel, timeout, reap và cleanup."""

    async def asyncSetUp(self) -> None:
        """Tạo cache riêng; fixture video dùng chung, không đụng nguồn của người dùng."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = Settings(
            database_path=self.root / "db", sources_path=self.root / "sources"
        )
        self.service = YoutubeService(self.settings)
        self.addAsyncCleanup(self.service.shutdown)
        self.fixture = self.root / "fixture.mp4"
        self.fixture.write_bytes(fixtures.video_bytes())
        self.processes = []
        self.mode = "ready"

    async def spawn(
        self, *args: object, **kwargs: object
    ) -> asyncio.subprocess.Process:
        """Tạo child thay worker, đọc đúng stdin và tạo video hoặc chờ bị kill."""
        if self.mode == "ready":
            script = "import sys,json,shutil; p=json.load(sys.stdin); shutil.copyfile(sys.argv[1],p['root']+'/video.mp4'); print(json.dumps({'title':'Test video','video_id':'jNQXAC9IVRw'}))"
        elif self.mode == "failed":
            script = "import sys;sys.exit(1)"
        else:
            script = "import time;time.sleep(60)"
        process = await SPAWN(sys.executable, "-c", script, str(self.fixture), **kwargs)
        self.processes.append(process)
        return process

    async def test_prepare_file_metadata_ttl_delete(self) -> None:
        """Job có file/thumbnail/metadata; get gia hạn, expiry và delete thu hồi cache."""
        with patch(
            "app.modules.youtube.service.asyncio.create_subprocess_exec",
            side_effect=self.spawn,
        ):
            job = self.service.create("https://youtu.be/jNQXAC9IVRw?si=secret")
            await self.service.tasks[job["id"]]
        current = self.service.get(job["id"])
        self.assertEqual(current["status"], "ready", current)
        self.assertEqual(current["metadata"]["width"], 160)
        self.assertTrue(self.service.content(job["id"]).is_file())
        self.assertTrue(self.service.content(job["id"], thumbnail=True).is_file())
        self.assertNotIn("secret", json.dumps(self.service.response(current)))
        current["expires"] = time.monotonic() - 1
        self.service.cleanup()
        self.assertFalse(self.service.jobs)
        self.assertFalse((self.service.root / job["id"]).exists())

    async def test_cancel_reaps_worker_and_queued_jobs(self) -> None:
        """Huỷ job queued hoặc downloading không để lại task, child hay file."""
        self.mode = "hold"
        with patch(
            "app.modules.youtube.service.asyncio.create_subprocess_exec",
            side_effect=self.spawn,
        ):
            first = self.service.create("https://youtu.be/jNQXAC9IVRw")
            for _ in range(100):
                if self.processes:
                    break
                await asyncio.sleep(0.01)
            queued = self.service.create("https://youtu.be/jNQXAC9IVRw")
            await self.service.delete(queued["id"])
            await self.service.delete(first["id"])
        self.assertFalse(self.service.tasks)
        self.assertFalse(self.service.jobs)
        self.assertTrue(
            all(process.returncode is not None for process in self.processes)
        )
        self.assertEqual(list(self.service.root.iterdir()), [])

    async def test_timeout_reaps_worker_and_removes_partial_files(self) -> None:
        """Download quá hạn phải failed và không giữ child hay cache dở dang."""
        self.mode = "hold"
        wait_for = asyncio.wait_for

        async def short_timeout(future: object, timeout: float) -> object:
            """Rút thời hạn worker trong test nhưng vẫn await và huỷ communicate thật."""
            return await wait_for(future, timeout=0.05)

        with (
            patch(
                "app.modules.youtube.service.asyncio.create_subprocess_exec",
                side_effect=self.spawn,
            ),
            patch(
                "app.modules.youtube.service.asyncio.wait_for",
                side_effect=short_timeout,
            ),
        ):
            job = self.service.create("https://youtu.be/jNQXAC9IVRw")
            await self.service.tasks[job["id"]]
        self.assertEqual(self.service.get(job["id"])["status"], "failed")
        self.assertFalse(self.service.tasks)
        self.assertTrue(
            all(process.returncode is not None for process in self.processes)
        )
        self.assertEqual(list(self.service.root.iterdir()), [])

    async def test_failure_is_sanitized_and_limit_enforced(self) -> None:
        """Worker lỗi có thông báo chung; job bị giới hạn bốn và không nhận URL ngoài YouTube."""
        self.mode = "failed"
        with patch(
            "app.modules.youtube.service.asyncio.create_subprocess_exec",
            side_effect=self.spawn,
        ):
            job = self.service.create("https://youtu.be/jNQXAC9IVRw")
            await self.service.tasks[job["id"]]
        self.assertEqual(self.service.get(job["id"])["status"], "failed")
        self.assertFalse((self.service.root / job["id"]).exists())
        with self.assertRaises(SourceError):
            self.service.create("https://private.invalid/video")
        self.mode = "hold"
        with patch(
            "app.modules.youtube.service.asyncio.create_subprocess_exec",
            side_effect=self.spawn,
        ):
            for _ in range(3):
                self.service.create("https://youtu.be/jNQXAC9IVRw")
            with self.assertRaises(SourceError) as error:
                self.service.create("https://youtu.be/jNQXAC9IVRw")
            self.assertEqual(error.exception.status_code, 429)
            await self.service.shutdown()
        self.assertFalse(self.service.tasks)


# ------------------------- Kiểm API video và inference ------------------------
class YoutubeApiTests(unittest.TestCase):
    """Tái dùng AI fixture để kiểm file Range và snapshot không phụ thuộc cache."""

    setUp = fixtures.RunTests.setUp
    make_client = fixtures.RunTests.make_client
    handle = fixtures.RunTests.handle
    wait = fixtures.RunTests.wait

    def test_ready_cache_preview_range_and_run_snapshot(self) -> None:
        """Preview tua bằng Range; AI dùng snapshot riêng, xoá cache không mất kết quả."""
        service = self.app.state.youtube
        job_id = "a" * 32
        root = service.root / job_id
        root.mkdir()
        (root / "video.mp4").write_bytes(fixtures.video_bytes())
        service.jobs[job_id] = {
            "id": job_id,
            "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
            "title": "Test",
            "status": "ready",
            "error": None,
            "metadata": {},
            "expires": time.monotonic() + 60,
        }
        response = self.client.get(
            f"/api/v1/youtube/sessions/{job_id}/content",
            headers={"Range": "bytes=0-19"},
        )
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(response.content), 20)
        started = self.client.post(
            "/api/v1/runs/youtube",
            json={"session_id": job_id, "model_id": self.model_id},
        )
        self.assertEqual(started.status_code, 202, started.text)
        self.client.delete(f"/api/v1/youtube/sessions/{job_id}")
        record = self.wait(started.json()["id"])
        self.assertEqual(record["status"], "completed", record)
        self.assertEqual(record["source_kind"], "video")
        self.assertEqual(
            self.client.get(f"/api/v1/runs/{record['id']}/preview").status_code, 200
        )
        self.assertEqual(self.app.state.sources.repository.count(), 0)
        self.assertEqual(
            self.client.get(f"/api/v1/youtube/sessions/{job_id}").status_code, 410
        )


# -------------------------- Kiểm bộ tải và giới hạn ---------------------------
class YoutubeWorkerTests(unittest.TestCase):
    """Kiểm yt-dlp options/hook và phân loại live mà không mở mạng."""

    def test_worker_has_bounded_video_selection_and_no_progress_stdout(self) -> None:
        """Chỉ chọn MP4/H264 hữu hạn và không làm nhiễu giao thức JSON stdout."""
        from yt_dlp.utils import DownloadError

        from app.modules.youtube.worker import prepare_video

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "video.mp4").write_bytes(b"fixture")
            with patch("app.modules.youtube.worker.YoutubeDL") as downloader:
                client = downloader.return_value.__enter__.return_value
                client.extract_info.return_value = {
                    "id": "jNQXAC9IVRw",
                    "title": "Title",
                    "duration": 19,
                }
                result = prepare_video(
                    {
                        "url": "https://youtu.be/jNQXAC9IVRw",
                        "root": str(root),
                        "limit": 10,
                    }
                )
                self.assertEqual(result["title"], "Title")
                options = downloader.call_args.args[0]
                self.assertTrue(options["noprogress"])
                self.assertTrue(options["noplaylist"])
                self.assertIn("height<=720", options["format"])
                with self.assertRaises(DownloadError):
                    options["progress_hooks"][0]({"downloaded_bytes": 11})
                for info, reason in [
                    ({"is_live": True}, "live"),
                    ({"live_status": "is_upcoming"}, "live"),
                    ({"duration": 14401}, "duration"),
                ]:
                    client.extract_info.return_value = info
                    client.process_ie_result.reset_mock()
                    with self.assertRaisesRegex(ValueError, reason):
                        prepare_video(
                            {
                                "url": "https://youtu.be/jNQXAC9IVRw",
                                "root": str(root),
                                "limit": 10,
                            }
                        )
                    client.process_ie_result.assert_not_called()
