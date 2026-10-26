"""Kiểm MediaMTX Docker thật với camera H264/TCP có xác thực loopback."""

import asyncio
import json
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.db import initialize_database
from app.modules.sources.repository import SourceRepository
from app.modules.sources.schemas import RtspSourceCreate
from app.modules.sources.service import SourceService
from app.modules.streams.service import PreviewService
from app.storage.local import LocalStorage
from tests.streams.rtsp_camera import RtspCamera

IMAGE = "bluenviron/mediamtx:1.21.3"


# --------------------------- Chọn cổng kiểm thử ------------------------------
def free_port() -> int:
    """Chọn cổng TCP/UDP cùng rảnh trên loopback cho dịch vụ fixture."""
    while True:
        with socket.socket() as tcp, socket.socket(type=socket.SOCK_DGRAM) as udp:
            tcp.bind(("127.0.0.1", 0))
            port = tcp.getsockname()[1]
            try:
                udp.bind(("127.0.0.1", port))
                return port
            except OSError:
                pass


# ------------------------ Tích hợp MediaMTX và RTSP --------------------------
@unittest.skipUnless(
    os.getenv("VISIONKIT_RUN_DOCKER_TESTS") == "1"
    and shutil.which("docker")
    and shutil.which("ffmpeg"),
    "Chạy VISIONKIT_RUN_DOCKER_TESTS=1 khi Docker và image MediaMTX sẵn sàng",
)
class RelayIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Relay thật, API thật, camera giả lập; không dùng camera vật lý/dữ liệu workspace."""

    async def asyncSetUp(self) -> None:
        """Mở relay riêng cổng ngẫu nhiên và camera Basic auth; encoder kết thúc trước test."""
        temporary = tempfile.TemporaryDirectory(prefix="visionkit-mtx-test-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        ports = set()
        while len(ports) < 3:
            ports.add(free_port())
        api, whep, ice = ports
        config = root / "mediamtx.yml"
        config.write_text(
            json.dumps(
                {
                    "logLevel": "error",
                    "logDestinations": ["file"],
                    "logFile": "/dev/null",
                    "api": True,
                    "apiAddress": f":{api}",
                    "authInternalUsers": [
                        {
                            "user": "any",
                            "pass": "",
                            "ips": [],
                            "permissions": [{"action": "api"}, {"action": "read"}],
                        }
                    ],
                    "rtsp": False,
                    "rtmp": False,
                    "hls": False,
                    "srt": False,
                    "moq": False,
                    "webrtc": True,
                    "webrtcAddress": f":{whep}",
                    "webrtcLocalUDPAddress": f":{ice}",
                    "webrtcIPsFromInterfaces": False,
                    "webrtcAdditionalHosts": ["127.0.0.1"],
                    "paths": {},
                }
            )
        )
        self.container = "visionkit-mtx-test-" + uuid4().hex[:12]
        self.process = await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "--rm",
            "--name",
            self.container,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--add-host",
            "host.docker.internal:host-gateway",
            "-v",
            f"{config}:/mediamtx.yml:ro",
            "-p",
            f"127.0.0.1:{api}:{api}/tcp",
            "-p",
            f"127.0.0.1:{whep}:{whep}/tcp",
            "-p",
            f"127.0.0.1:{ice}:{ice}/udp",
            IMAGE,
            "/mediamtx.yml",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.addAsyncCleanup(self.stop_relay)
        self.settings = Settings(
            database_path=root / "db",
            sources_path=root / "sources",
            mediamtx_api_url=f"http://127.0.0.1:{api}",
            mediamtx_webrtc_url=f"http://127.0.0.1:{whep}",
        )
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                try:
                    response = await client.get(f"http://127.0.0.1:{api}/v3/info")
                    if response.is_success:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                self.fail("MediaMTX fixture chưa sẵn sàng.")
        self.camera = RtspCamera()
        await self.camera.start(host="0.0.0.0")
        self.addAsyncCleanup(self.camera.close)
        database = initialize_database(self.settings.database_path)
        self.sources = SourceService(
            SourceRepository(database), LocalStorage(self.settings)
        )
        self.service = PreviewService(self.sources, self.settings)
        self.addAsyncCleanup(self.service.shutdown)

    async def stop_relay(self) -> None:
        """Xoá đúng container fixture và đợi Docker CLI kết thúc."""
        cleanup = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "--force",
            self.container,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await cleanup.wait()
        await self.process.wait()

    def source(self, password: str) -> str:
        """Tạo camera có credentials fixture trong DB tạm, trả source ID."""
        return self.sources.create_rtsp(
            RtspSourceCreate(
                name="Fixture",
                url=f"rtsp://user:{password}@host.docker.internal:{self.camera.port}/live",
            )
        ).id

    async def wait_status(self, token: str, status: str) -> dict:
        """Poll tối đa năm giây để MediaMTX hoàn tất kết nối/challenge Basic auth."""
        for _ in range(50):
            result = await self.service.status(token)
            if result["status"] == status:
                return result
            await asyncio.sleep(0.1)
        self.fail(f"Không đạt {status}; trạng thái: {result}")

    async def test_unsaved_camera_checks_auth_without_creating_library_source(
        self,
    ) -> None:
        """MediaMTX đọc được URL tạm; sai auth được báo đúng và DB vẫn hoàn toàn trống."""
        self.assertEqual(self.sources.repository.count(), 0)
        identity = str(uuid4())
        lease = await self.service.create_temporary(
            identity, f"rtsp://user:good@host.docker.internal:{self.camera.port}/live"
        )
        result = await self.wait_status(lease["id"], "ready")
        self.assertEqual(result["auth"], "accepted")
        self.assertEqual(self.sources.repository.count(), 0)
        await self.service.close(lease["id"])
        self.assertFalse(self.service.temporary_urls)
        lease = await self.service.create_temporary(
            identity,
            f"rtsp://user:wrong-secret@host.docker.internal:{self.camera.port}/live",
        )
        result = await self.wait_status(lease["id"], "error")
        self.assertEqual(result["code"], "auth_failed")
        self.assertNotIn("wrong-secret", json.dumps(result))
        self.assertEqual(self.sources.repository.count(), 0)
        await self.service.close(lease["id"])
        self.assertFalse(self.service.paths)
        self.assertFalse(self.service.temporary_urls)

    async def test_real_authenticated_read_shared_camera_and_cleanup(self) -> None:
        """Credentials đúng đọc H264, hai viewer dùng một RTSP connection, stop gỡ path."""
        sid = self.source("good")
        first = await self.service.create(sid)
        result = await self.wait_status(first["id"], "ready")
        self.assertEqual(result["auth"], "accepted")
        self.assertIn("H264", result["codecs"])
        second = await self.service.create(sid)
        await asyncio.sleep(0.1)
        self.assertEqual(self.camera.connections, 1)
        await self.service.close(first["id"])
        self.assertIn(sid, self.service.paths)
        await self.service.close(second["id"])
        response = await self.service.api.get(f"/v3/paths/get/{self.service.path(sid)}")
        self.assertEqual(response.status_code, 404)

    async def test_real_wrong_password_rejected_and_edit_recovers(self) -> None:
        """401 thật qua lastError phân biệt với online; sửa URL khôi phục được luồng."""
        sid = self.source("wrong-password")
        lease = await self.service.create(sid)
        result = await self.wait_status(lease["id"], "error")
        self.assertEqual(result["auth"], "rejected")
        self.assertEqual(result["code"], "auth_failed")
        self.assertNotIn("wrong-password", json.dumps(result))
        self.sources.repository.update(
            sid,
            location=f"rtsp://user:good@host.docker.internal:{self.camera.port}/live",
        )
        await self.service.restart(sid)
        result = await self.wait_status(lease["id"], "ready")
        self.assertEqual(result["auth"], "accepted")
