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

    def test_counting_service_reconnects_rtsp_and_releases_every_lease(self) -> None:
        """Nối lượt RTSP hết hạn, thử lại EOF và Dừng từ cấu hình không giữ relay mồ côi."""
        self.app.state.counting_supervisor.paused = True
        supervisor = self.app.state.counting_supervisor
        self.app.state.models.repository.configure(self.model_id, "yoloe", "segment")
        sid = self.source()["id"]
        signature = self.client.get(f"/api/v1/counting/sources/{sid}").json()[
            "source_signature"
        ]
        response = self.client.post(
            "/api/v1/counting/profiles",
            json={
                "name": "Camera continuous",
                "source_id": sid,
                "source_signature": signature,
                "config": {
                    "reference_width": 64,
                    "reference_height": 32,
                    "zones": [
                        {
                            "id": str(uuid4()),
                            "name": "Camera",
                            "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                        }
                    ],
                },
                "monitor": {
                    "model_id": self.model_id,
                    "continuous": True,
                    "duration_seconds": 60,
                },
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        pid = response.json()["id"]
        endpoint = f"/api/v1/counting/profiles/{pid}"
        first = self.client.post(endpoint + "/runs").json()
        self.assertEqual(self.wait(first["id"])["completion_reason"], "duration_limit")
        self.hold = True
        self.client.portal.call(supervisor.tick)
        second = self.client.get(endpoint).json()
        self.assertNotEqual(second["current_run_id"], first["id"])
        owner = self.client.get(f"/api/v1/counting/sources/{sid}").json()
        self.assertEqual(owner["owner_profile_id"], pid)
        self.assertTrue(owner["enabled"])
        self.assertNotIn("very-private", json.dumps(second))
        self.client.post(endpoint + "/stop")
        self.assertFalse(self.app.state.runs.relay_leases)
        self.assertFalse(self.app.state.streams.viewers)
        self.client.portal.call(supervisor.tick)
        self.assertEqual(
            self.client.get(endpoint).json()["current_run_id"], second["current_run_id"]
        )

    def test_counting_rtsp_snapshot_cancel_and_redaction(self) -> None:
        """Đếm RTSP dùng relay chung, lưu vùng và nhả lease khi dừng; không lộ URL."""
        self.hold = True
        self.app.state.models.repository.configure(self.model_id, "yoloe", "segment")
        sid = self.source()["id"]
        endpoint = f"/api/v1/counting/sources/{sid}"
        initial = self.client.get(endpoint).json()
        config = {
            "reference_width": 64,
            "reference_height": 32,
            "zones": [
                {
                    "id": str(uuid4()),
                    "name": "Camera zone",
                    "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                }
            ],
        }
        save = self.client.put(
            endpoint,
            json={"source_signature": initial["source_signature"], "config": config},
        )
        self.assertEqual(save.status_code, 200, save.text)
        response = self.client.post(
            "/api/v1/counting/runs",
            json={
                "source_id": sid,
                "model_id": self.model_id,
                "source_signature": initial["source_signature"],
                "config": config,
                "duration_seconds": 10,
            },
        )
        self.assertEqual(response.status_code, 202, response.text)
        rid = response.json()["id"]
        for _ in range(100):
            record = self.client.get(f"/api/v1/runs/{rid}").json()
            if record["counts"]:
                break
            time.sleep(0.01)
        self.assertTrue(record["counts"]["valid"], record)
        self.assertEqual(record["counts"]["regions"][0]["counts"]["person"], 0)
        self.assertNotIn("very-private", json.dumps(record))
        self.assertNotIn("counting", self.payload)
        self.assertEqual(self.client.get(endpoint).json()["current_run_id"], rid)
        updated = self.client.put(
            endpoint,
            json={
                "source_signature": initial["source_signature"],
                "config": config,
                "monitor": {
                    "model_id": self.model_id,
                    "options": {"conf": 0.8},
                    "duration_seconds": 3600,
                },
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["monitor"]["options"]["conf"], 0.8)
        self.assertEqual(
            self.client.get(f"/api/v1/runs/{rid}").json()["options"]["conf"], 0.25
        )
        duplicate = self.client.post(
            "/api/v1/counting/runs",
            json={
                "source_id": sid,
                "model_id": self.model_id,
                "source_signature": initial["source_signature"],
                "config": config,
            },
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(
            self.client.delete(f"/api/v1/runs/{rid}").json()["status"], "cancelled"
        )
        self.assertFalse(self.app.state.streams.viewers)
        self.assertFalse(self.app.state.runs.relay_leases)
        # Lưu vùng sau run không làm mất cấu hình nguồn; dọn run giữ cả nguồn/vùng.
        self.client.delete(f"/api/v1/runs/{rid}/resources")
        self.assertEqual(len(self.client.get(endpoint).json()["config"]["zones"]), 1)
        self.assertIsNone(self.client.get(endpoint).json()["current_run_id"])

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
