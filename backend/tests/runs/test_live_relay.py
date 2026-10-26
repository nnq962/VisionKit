"""Kiểm vòng đời AI đọc relay và bảo vệ camera đang xử lý."""

import json
import time
import unittest
from uuid import uuid4

import httpx

from tests.runs import test_rtsp as fixtures


# ------------------------ Kiểm AI dùng chung relay ---------------------------
class LiveRelayTests(unittest.TestCase):
    """Dùng DB thật và AI/MediaMTX giả để kiểm lease độc lập browser và cleanup."""

    setUp = fixtures.RtspApiTests.setUp
    make_client = fixtures.RtspApiTests.make_client
    wait = fixtures.RtspApiTests.wait
    source = fixtures.RtspApiTests.source
    hold = False
    live_error = False
    early_eof = False
    closed = 0
    url = fixtures.RtspApiTests.url

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """Trả config relay thành công, giữ nguyên fixture inference stream có thể huỷ."""
        if request.url.port == 9997:
            return httpx.Response(200)
        return await fixtures.RtspApiTests.handle(self, request)

    def start(self, **selection: str) -> httpx.Response:
        """Tạo run relay không truyền credential camera từ web."""
        return self.client.post(
            "/api/v1/runs/live",
            json={"model_id": self.model_id, "duration_seconds": 2, **selection},
        )

    def test_saved_relay_payload_and_terminal_release(self) -> None:
        """AI nhận URL MediaMTX, run không lộ bí mật và terminal nhả relay/model."""
        sid = self.source()["id"]
        response = self.start(source_id=sid)
        self.assertEqual(response.status_code, 202, response.text)
        record = self.wait(response.json()["id"])
        self.assertEqual(record["status"], "completed")
        self.assertEqual(
            self.payload["stream_url"], f"rtsp://127.0.0.1:8554/visionkit_{sid}"
        )
        self.assertEqual(self.payload["options"]["max_fps"], 5)
        self.assertNotIn("very-private", json.dumps(record))
        for _ in range(100):
            if not self.app.state.streams.viewers:
                break
            time.sleep(0.01)
        self.assertFalse(self.app.state.streams.viewers)
        self.assertFalse(self.app.state.runs.relay_leases)

    def test_temporary_run_outlives_browser_and_cancel_reclaims_url(self) -> None:
        """Đóng browser không dừng AI; huỷ AI cuối cùng mới xoá URL/path tạm."""
        self.hold = True
        pid = str(uuid4())
        viewer = self.client.post(
            "/api/v1/streams/temporary/sessions",
            json={"preview_id": pid, "url": self.url},
        ).json()
        response = self.start(preview_id=pid)
        self.assertEqual(response.status_code, 202, response.text)
        rid = response.json()["id"]
        self.client.delete(f"/api/v1/streams/sessions/{viewer['id']}")
        self.assertTrue(self.app.state.streams.temporary_urls)
        self.assertEqual(len(self.app.state.streams.viewers), 1)
        self.assertEqual(self.app.state.sources.repository.count(), 0)
        stopped = self.client.delete(f"/api/v1/runs/{rid}")
        self.assertEqual(stopped.json()["status"], "cancelled")
        self.assertFalse(self.app.state.streams.viewers)
        self.assertFalse(self.app.state.streams.temporary_urls)
        self.assertFalse(self.app.state.runs.relay_leases)

    def test_queue_cancel_and_active_source_protection(self) -> None:
        """Huỷ job chờ nhả riêng lease; sửa/xoá camera cần chờ mọi AI dừng."""
        self.hold = True
        sid = self.source()["id"]
        records = [self.start(source_id=sid).json() for _ in range(4)]
        self.assertEqual(self.start(source_id=sid).status_code, 429)
        self.assertEqual(len(self.app.state.streams.viewers), 4)
        self.assertEqual(self.client.delete(f"/api/v1/sources/{sid}").status_code, 409)
        self.assertEqual(
            self.client.put(
                f"/api/v1/sources/{sid}/rtsp", json={"name": "New", "url": self.url}
            ).status_code,
            409,
        )
        self.client.delete(f"/api/v1/runs/{records[1]['id']}")
        self.assertEqual(len(self.app.state.streams.viewers), 3)
        for record in records:
            self.client.delete(f"/api/v1/runs/{record['id']}")
        self.assertFalse(self.app.state.streams.viewers)
        self.assertEqual(self.client.delete(f"/api/v1/sources/{sid}").status_code, 204)

    def test_invalid_selection_and_model_rollback(self) -> None:
        """Thiếu/hai nguồn và phiên hết hạn bị từ chối, model lỗi không để lại lease."""
        self.assertEqual(self.start().status_code, 422)
        self.assertEqual(self.start(preview_id=str(uuid4())).status_code, 410)
        sid = self.source()["id"]
        self.assertEqual(
            self.start(source_id=sid, preview_id=str(uuid4())).status_code, 422
        )
        response = self.client.post(
            "/api/v1/runs/live", json={"source_id": sid, "model_id": "missing"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.app.state.streams.viewers)
