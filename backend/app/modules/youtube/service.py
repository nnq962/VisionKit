"""Job chuẩn bị YouTube có giới hạn tài nguyên, TTL và cleanup; không ghi thư viện."""

import asyncio
import json
import os
import re
import shutil
import signal
import sys
import time
from pathlib import Path
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import SourceError
from app.core.youtube import normalize_youtube_url
from app.storage.video_processing import inspect_video


# ------------------------- Quản lý video YouTube tạm --------------------------
class YoutubeService:
    """Giữ tối đa bốn job trong RAM và file cache riêng, tự hết hạn sau một giờ.

    Worker có timeout ba phút và một download đồng thời. Run AI sao chép video
    vào snapshot riêng trước khi trả 202, vì vậy cleanup job không ngắt inference.
    """

    def __init__(self, settings: Settings) -> None:
        """Nhận settings; tạo cache riêng cạnh sources, không thay đổi dữ liệu thư viện."""
        self.settings = settings
        self.root = settings.sources_path.parent / "youtube-cache"
        self.root.mkdir(parents=True, exist_ok=True)
        # Job không tồn tại qua restart; chỉ dọn thư mục UUID do module quản lý.
        for child in self.root.iterdir():
            if child.is_dir() and re.fullmatch(r"[0-9a-f]{32}", child.name):
                shutil.rmtree(child, ignore_errors=True)
        self.jobs: dict[str, dict] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.semaphore = asyncio.Semaphore(1)
        self.closed = False

    def create(self, url: str) -> dict:
        """Chuẩn hoá URL, tạo job queued; trả 429 khi đủ bốn job, không mở mạng tại đây."""
        if self.closed:
            raise SourceError(503, "Dịch vụ YouTube đang dừng.")
        self.cleanup()
        if len(self.jobs) >= 4:
            raise SourceError(429, "Đã có bốn video tạm. Xoá một video trước khi thêm.")
        try:
            canonical = normalize_youtube_url(url)
        except ValueError as error:
            raise SourceError(422, str(error)) from None
        job_id = uuid4().hex
        job = {
            "id": job_id,
            "url": canonical,
            "status": "queued",
            "title": "YouTube",
            "error": None,
            "metadata": {},
            "expires": time.monotonic() + 3600,
        }
        self.jobs[job_id] = job
        self.tasks[job_id] = asyncio.create_task(
            self.prepare(job), name=f"youtube:{job_id}"
        )
        return self.response(job)

    def get(self, job_id: str) -> dict:
        """Lấy job còn hạn, gia hạn TTL; trả 410 nếu mất cache hoặc service đã restart."""
        job = self.jobs.get(job_id)
        if job is None or job["expires"] < time.monotonic():
            raise SourceError(
                410, "Video YouTube tạm đã hết hạn. Chuẩn bị lại liên kết."
            )
        job["expires"] = time.monotonic() + 3600
        return job

    def response(self, job: dict) -> dict:
        """Chỉ trả metadata công khai, không trả đường dẫn cache hay URL ký của YouTube."""
        return {
            key: job[key]
            for key in ["id", "url", "status", "title", "error", "metadata"]
        }

    async def prepare(self, job: dict) -> None:
        """Chạy worker giới hạn ba phút, xác minh file; huỷ/lỗi đều dọn file và reap worker."""
        root = self.root / job["id"]
        process = None
        try:
            async with self.semaphore:
                job["status"] = "preparing"
                root.mkdir()
                spawning = asyncio.create_task(
                    asyncio.create_subprocess_exec(
                        sys.executable,
                        "-m",
                        "app.modules.youtube.worker",
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        start_new_session=True,
                        cwd=Path(__file__).resolve().parents[3],
                    )
                )
                try:
                    process = await asyncio.shield(spawning)
                except asyncio.CancelledError:
                    process = await spawning
                    raise
                payload = json.dumps(
                    {
                        "url": job["url"],
                        "root": str(root),
                        "limit": self.settings.max_video_upload_bytes,
                    }
                ).encode()
                stdout, _ = await asyncio.wait_for(
                    process.communicate(payload), timeout=180
                )
                if process.returncode or len(stdout) > 16384:
                    raise SourceError(
                        422,
                        "Không chuẩn bị được video. Kiểm tra video công khai, giới hạn dung lượng hoặc thử lại sau.",
                    )
                details = json.loads(stdout)
                if "error" in details:
                    raise SourceError(422, details["error"])
                metadata, thumbnail = await run_in_threadpool(
                    inspect_video, root / "video.mp4"
                )
                metadata.pop("extension", None)
                metadata.update(size=(root / "video.mp4").stat().st_size)
                (root / "thumbnail.jpg").write_bytes(thumbnail)
                job.update(status="ready", title=details["title"], metadata=metadata)
        except asyncio.CancelledError:
            job.update(status="cancelled")
            raise
        except Exception as error:
            job.update(
                status="failed",
                error=error.message
                if isinstance(error, SourceError)
                else "Không chuẩn bị được YouTube trong thời gian cho phép. Thử lại sau.",
            )
        finally:
            if process:
                if process.returncode is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                await process.wait()
            if job["status"] != "ready":
                shutil.rmtree(root, ignore_errors=True)
            self.tasks.pop(job["id"], None)

    def content(self, job_id: str, *, thumbnail: bool = False) -> Path:
        """Trả file đã xác minh cho FileResponse/inference; từ chối job chưa ready."""
        job = self.get(job_id)
        if job["status"] != "ready":
            raise SourceError(409, "Video YouTube chưa sẵn sàng.")
        path = self.root / job_id / ("thumbnail.jpg" if thumbnail else "video.mp4")
        if not path.is_file():
            raise SourceError(410, "File YouTube tạm không còn. Chuẩn bị lại liên kết.")
        return path

    async def delete(self, job_id: str) -> None:
        """Huỷ job, đợi thu hồi worker rồi xoá cache, không xoá snapshot AI đã tạo."""
        task = self.tasks.get(job_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.tasks.pop(job_id, None)
        self.jobs.pop(job_id, None)
        shutil.rmtree(self.root / job_id, ignore_errors=True)

    def cleanup(self) -> None:
        """Dọn cache terminal hết hạn; job active được timeout riêng nên không xoá giữa download."""
        for job_id, job in list(self.jobs.items()):
            if job_id not in self.tasks and job["expires"] < time.monotonic():
                self.jobs.pop(job_id)
                shutil.rmtree(self.root / job_id, ignore_errors=True)

    async def maintain(self) -> None:
        """Dọn cache hết hạn mỗi phút khi service sống."""
        while True:
            await asyncio.sleep(60)
            self.cleanup()

    async def shutdown(self) -> None:
        """Ngăn job mới, huỷ/reap mọi worker và dọn toàn bộ cache module quản lý."""
        self.closed = True
        for job_id in list(self.jobs):
            await self.delete(job_id)
