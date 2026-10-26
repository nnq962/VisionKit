"""Kiểm API MediaMTX, WHEP, lease và phân loại xác thực, không xử lý frame."""

import asyncio
import json
import tempfile
import time
import unittest
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from fastapi.routing import APIWebSocketRoute
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import SourceError
from app.main import create_app
from app.modules.runs.router import router as runs_router
from app.modules.streams.router import router as streams_router
from app.modules.streams.service import PreviewService


# ---------------------------- Kiểm registry relay ----------------------------
class PreviewTests(unittest.IsolatedAsyncioTestCase):
    """DB nguồn thật, HTTP MediaMTX giả lập có contract v1.21.3."""

    async def asyncSetUp(self) -> None:
        """Tạo nguồn RTSP và registry riêng trong loop test, không đụng camera thật."""
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.settings = Settings(
            database_path=root / "db", sources_path=root / "sources"
        )
        self.app = create_app(self.settings)
        self.client = self.stack.enter_context(TestClient(self.app))
        record = self.client.post(
            "/api/v1/sources/rtsp",
            json={
                "name": "Cam",
                "url": "rtsp://operator:very-secret@localhost/live?token=private",
            },
        ).json()
        self.sid = record["id"]
        self.service = PreviewService(self.app.state.sources, self.settings)
        self.requests = []
        self.online = False
        self.error = ""
        self.configured = False
        self.location = None
        self.service.api = httpx.AsyncClient(
            base_url=self.settings.mediamtx_api_url,
            transport=httpx.MockTransport(self.api),
        )
        self.service.whep = httpx.AsyncClient(
            base_url=self.settings.mediamtx_webrtc_url,
            transport=httpx.MockTransport(self.whep),
        )
        self.addAsyncCleanup(self.service.shutdown)

    def api(self, request: httpx.Request) -> httpx.Response:
        """Mô phỏng config/paths và static-sources; ghi body để kiểm URL thật ở server."""
        self.requests.append(request)
        path = request.url.path
        if "/config/paths/replace/" in path:
            return httpx.Response(200 if self.configured else 404)
        if "/config/paths/add/" in path:
            self.configured = True
            return httpx.Response(200)
        if "/config/paths/delete/" in path:
            self.configured = False
            return httpx.Response(200)
        if "/static-sources/" in path:
            return httpx.Response(200, json={"state": "error", "lastError": self.error})
        return httpx.Response(
            200,
            json={
                "online": True,
                "available": self.online,
                "tracks2": [{"codec": "H264"}],
            },
        )

    def whep(self, request: httpx.Request) -> httpx.Response:
        """Trả SDP/Location theo WHEP; DELETE được ghi lại để kiểm thu hồi session."""
        self.requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(200)
        location = self.location or f"/{self.service.path(self.sid)}/whep/test-session"
        return httpx.Response(201, text="v=0\r\nanswer", headers={"Location": location})

    async def test_temporary_preview_never_saves_source_and_cleans_last_lease(
        self,
    ) -> None:
        """Kiểm URL chưa lưu chỉ dùng RAM/MediaMTX; hai viewer và cleanup không ghi DB."""
        before = self.service.sources.repository.count()
        url = "rtsp://user:temporary-secret@localhost/live?token=temporary-token"
        first = await self.service.create_temporary(self.sid, url)
        second = await self.service.create_temporary(self.sid, url)
        key = f"temporary_{self.sid}"
        self.assertIn(key, self.service.paths)
        self.assertEqual(self.service.temporary_urls[key], url)
        self.assertNotIn("temporary-secret", json.dumps(first))
        self.assertEqual(self.service.sources.repository.count(), before)
        self.assertEqual(len([r for r in self.requests if r.method == "POST"]), 2)
        self.online = True
        result = await self.service.status(first["id"])
        self.assertEqual(result["status"], "ready")
        await self.service.close(first["id"])
        self.assertIn(key, self.service.temporary_urls)
        await self.service.close(second["id"])
        self.assertNotIn(key, self.service.temporary_urls)
        self.assertNotIn(key, self.service.paths)
        self.assertEqual(self.service.sources.repository.count(), before)

    async def test_temporary_limits_conflicts_and_failed_creation_do_not_leak_urls(
        self,
    ) -> None:
        """Không đổi URL phiên đang dùng; giới hạn path chung và lỗi API không giữ URL rác."""
        lease = await self.service.create_temporary(self.sid, "rtsp://first/live")
        with self.assertRaises(SourceError) as conflict:
            await self.service.create_temporary(self.sid, "rtsp://second/live")
        self.assertEqual(conflict.exception.status_code, 409)
        await self.service.close(lease["id"])
        self.service.paths.update({"one", "two", "three", "four"})
        with self.assertRaises(SourceError) as limit:
            await self.service.create_temporary(self.sid, "rtsp://first/live")
        self.assertEqual(limit.exception.status_code, 429)
        self.assertFalse(self.service.temporary_urls)
        self.service.paths.clear()
        self.service.api_request = AsyncMock(
            side_effect=[
                SourceError(503, "MediaMTX chưa sẵn sàng."),
                httpx.Response(404),
            ]
        )
        with self.assertRaises(SourceError):
            await self.service.create_temporary(self.sid, "rtsp://first/live")
        self.assertFalse(self.service.temporary_urls)
        self.assertFalse(self.service.viewers)

    async def test_cancelled_temporary_creation_reclaims_uncertain_relay_path(
        self,
    ) -> None:
        """Huỷ POST sau khi gửi có thể đã tạo path; vẫn thử DELETE và bỏ URL tạm."""
        self.service.api_request = AsyncMock(
            side_effect=[asyncio.CancelledError(), httpx.Response(404)]
        )
        with self.assertRaises(asyncio.CancelledError):
            await self.service.create_temporary(
                self.sid, "rtsp://user:secret@localhost/live"
            )
        self.assertEqual(self.service.api_request.await_args_list[-1].args[0], "DELETE")
        self.assertFalse(self.service.temporary_urls)
        self.assertFalse(self.service.paths)
        self.assertFalse(self.service.viewers)

    async def test_shared_path_and_no_credentials_in_public_session(self) -> None:
        """Hai viewer chỉ đăng ký một path; response không có URL/password camera."""
        first = await self.service.create(self.sid)
        second = await self.service.create(self.sid)
        self.assertNotEqual(first["id"], second["id"])
        configured = [r for r in self.requests if r.method == "POST"]
        self.assertEqual(len(configured), 2)  # replace 404 rồi add
        payload = json.loads(configured[-1].content)
        self.assertIn("very-secret", payload["source"])
        self.assertEqual(payload["rtspTransport"], "tcp")
        self.assertNotIn("very-secret", json.dumps(first))
        await self.service.close(first["id"])
        self.assertTrue(self.configured)
        await self.service.close(second["id"])
        self.assertFalse(self.configured)

    async def test_docker_loopback_mapping_preserves_saved_url_and_credentials(
        self,
    ) -> None:
        """Chỉ URL nội bộ chuyển sang host Docker; DB giữ nguyên localhost/credentials."""
        self.service.settings = replace(
            self.settings, mediamtx_source_host="host.docker.internal"
        )
        await self.service.create(self.sid)
        payload = json.loads(self.requests[-1].content)
        self.assertEqual(
            payload["source"],
            "rtsp://operator:very-secret@host.docker.internal/live?token=private",
        )
        self.assertIn("@localhost/", self.service.sources.get(self.sid).location)

    async def test_camera_auth_is_based_on_api_errors_and_successful_read(self) -> None:
        """Chỉ trả rejected khi MediaMTX thực sự báo 401/403; offline là unknown."""
        lease = await self.service.create(self.sid)
        for error in [
            "bad status code: 401 (Unauthorized)",
            "403 Forbidden rtsp://secret@camera",
        ]:
            self.error = error
            result = await self.service.status(lease["id"])
            self.assertEqual(result["code"], "auth_failed")
            self.assertFalse(result["retryable"])
            self.assertNotIn("secret", json.dumps(result))
        self.error = "dial tcp: i/o timeout rtsp://very-secret@camera"
        result = await self.service.status(lease["id"])
        self.assertEqual(result["auth"], "unknown")
        self.assertEqual(result["status"], "reconnecting")
        self.assertNotIn("very-secret", json.dumps(result))
        self.online = True
        result = await self.service.status(lease["id"])
        self.assertEqual(result["auth"], "accepted")
        self.assertEqual(result["codecs"], ["H264"])

    async def test_whep_offer_cleanup_and_untrusted_location(self) -> None:
        """SDP được proxy; Location ngoài origin không được dùng để gửi DELETE."""
        lease = await self.service.create(self.sid)
        answer = await self.service.offer(lease["id"], "v=0\r\noffer")
        self.assertIn("answer", answer)
        self.assertEqual(self.requests[-1].content, b"v=0\r\noffer")
        await self.service.close(lease["id"])
        self.assertTrue(
            any(r.method == "DELETE" and "/whep/" in r.url.path for r in self.requests)
        )
        lease = await self.service.create(self.sid)
        self.location = "http://external.invalid/private"
        with self.assertRaises(SourceError):
            await self.service.offer(lease["id"], "v=0")
        self.assertIsNone(self.service.viewers[lease["id"]].upstream)

    async def test_expiry_restart_and_deleted_source(self) -> None:
        """Heartbeat gia hạn, restart cập nhật URL, remove thu hồi mọi lease/path."""
        lease = await self.service.create(self.sid)
        viewer = self.service.viewer(lease["id"])
        old_expiry = viewer.expires
        await asyncio.sleep(0.001)
        await self.service.status(lease["id"])
        self.assertGreater(viewer.expires, old_expiry)
        self.service.sources.repository.update(self.sid, location="rtsp://changed/live")
        await self.service.restart(self.sid)
        self.assertEqual(
            json.loads(self.requests[-1].content)["source"], "rtsp://changed/live"
        )
        viewer.expires = time.monotonic() - 1
        with self.assertRaises(SourceError) as error:
            self.service.viewer(lease["id"])
        self.assertEqual(error.exception.status_code, 410)
        await self.service.remove(self.sid)
        self.assertFalse(self.service.viewers)
        self.assertFalse(self.service.paths)

    async def test_unavailable_media_does_not_leak_paths_or_leases(self) -> None:
        """MediaMTX lỗi không tạo lease và không phản chiếu response bí mật."""
        self.service.api_request = AsyncMock(
            side_effect=SourceError(503, "MediaMTX chưa sẵn sàng.")
        )
        with self.assertRaises(SourceError):
            await self.service.create(self.sid)
        self.assertFalse(self.service.viewers)
        self.assertFalse(self.service.paths)


# -------------------------- Kiểm HTTP signaling ------------------------------
class PreviewApiTests(unittest.TestCase):
    """Đảm bảo endpoint chỉ trả lease/status/SDP; preview WebSocket cũ đã bỏ."""

    def test_preview_has_no_websocket_transport_and_inference_events_remain(
        self,
    ) -> None:
        """Preview chỉ dùng WHEP/HTTP; WebSocket kết quả AI vẫn thuộc namespace runs."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = create_app(
                Settings(database_path=root / "db", sources_path=root / "sources")
            )
            websocket_paths = {
                route.path
                for route in (*streams_router.routes, *runs_router.routes)
                if isinstance(route, APIWebSocketRoute)
            }
            self.assertFalse(
                any(path.startswith("/streams/") for path in websocket_paths)
            )
            self.assertIn("/runs/{run_id}/events", websocket_paths)
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/streams/c6b04bdd-3129-44c9-8675-206453ceec25/preview"
                )
                self.assertEqual(response.status_code, 404)

    def test_unsaved_url_endpoint_and_secret_validation(self) -> None:
        """Nút kiểm tra gọi API tạm, không cần tên/source; URL lỗi không bị phản chiếu."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = create_app(
                Settings(database_path=root / "db", sources_path=root / "sources")
            )
            with TestClient(app) as client:
                token = "c6b04bdd-3129-44c9-8675-206453ceec25"
                service = app.state.streams
                service.create_temporary = AsyncMock(return_value={"id": token})
                url = "rtsp://user:temporary-secret@localhost/live"
                response = client.post(
                    "/api/v1/streams/temporary/sessions",
                    json={"preview_id": token, "url": url},
                )
                self.assertEqual(response.status_code, 201)
                service.create_temporary.assert_awaited_once_with(token, url)
                self.assertNotIn("temporary-secret", response.text)
                self.assertEqual(client.get("/api/v1/sources").json()["total"], 0)
                response = client.post(
                    "/api/v1/streams/temporary/sessions",
                    json={
                        "preview_id": token,
                        "url": "http://user:temporary-secret@localhost/live",
                    },
                )
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("temporary-secret", response.text)

    def test_session_endpoints_and_sdp_limits(self) -> None:
        """Route forward đúng service, kiểm MIME/size và đóng idempotent."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = create_app(
                Settings(database_path=root / "db", sources_path=root / "sources")
            )
            with TestClient(app) as client:
                service = app.state.streams
                token = "c6b04bdd-3129-44c9-8675-206453ceec25"
                service.create = AsyncMock(return_value={"id": token})
                service.status = AsyncMock(
                    return_value={
                        "status": "ready",
                        "auth": "accepted",
                        "codecs": ["H264"],
                    }
                )
                service.offer = AsyncMock(return_value="v=0\r\nanswer")
                service.close = AsyncMock()
                response = client.post(f"/api/v1/streams/{token}/sessions")
                self.assertEqual(response.status_code, 201)
                self.assertEqual(
                    client.get(f"/api/v1/streams/sessions/{token}").json()["auth"],
                    "accepted",
                )
                path = f"/api/v1/streams/sessions/{token}/whep"
                self.assertEqual(client.post(path, content="v=0").status_code, 415)
                self.assertEqual(
                    client.post(
                        path,
                        content=b"x" * (256 * 1024 + 1),
                        headers={"Content-Type": "application/sdp"},
                    ).status_code,
                    413,
                )
                self.assertEqual(
                    client.post(
                        path, content="v=0", headers={"Content-Type": "application/sdp"}
                    ).text,
                    "v=0\r\nanswer",
                )
                self.assertEqual(
                    client.delete(f"/api/v1/streams/sessions/{token}").status_code, 204
                )
