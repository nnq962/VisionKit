"""Kiểm camera local qua API, JPEG HTTP riêng và cleanup lượt chạy."""

import base64
import json
import time
import unittest
from collections.abc import AsyncIterator
from io import BytesIO

import httpx
from PIL import Image

from tests.runs import test_rtsp as fixtures


# -------------------------- Stream webcam giả lập ----------------------------
class WebcamStream(httpx.AsyncByteStream):
    """Tái sử dụng frame live, thêm preview JPEG chỉ ở kênh AI nội bộ."""

    def __init__(self, owner: "WebcamApiTests") -> None:
        """Giữ fixture có chế độ hold/cancel và JPEG đã encode."""
        self.owner = owner

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Đính kèm JPEG khi có frame; không thay đổi result/terminal contract."""
        async for raw in fixtures.LiveStream(self.owner):
            event = json.loads(raw)
            if event["type"] == "frame":
                event["preview_jpeg"] = base64.b64encode(self.owner.jpeg).decode()
            yield (json.dumps(event) + "\n").encode()


# ---------------------------- Kiểm API webcam --------------------------------
class WebcamApiTests(unittest.TestCase):
    """DB thật, AI HTTP giả; không mở webcam vật lý trong unit tests."""

    make_client = fixtures.RtspApiTests.make_client
    wait = fixtures.RtspApiTests.wait
    hold = False
    early_eof = False
    live_error = False
    closed = 0
    url = "unused"

    def setUp(self) -> None:
        """Tạo model fixture và JPEG nhỏ, giữ nguồn/MediaMTX rỗng."""
        fixtures.RtspApiTests.setUp(self)
        buffer = BytesIO()
        Image.new("RGB", (64, 32), "red").save(buffer, format="JPEG")
        self.jpeg = buffer.getvalue()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """AI nhận đúng device_index, không nhận URL và không tạo relay MediaMTX."""
        if request.url.path.endswith("/webcams/check"):
            return httpx.Response(
                200,
                json={
                    "device_index": 0,
                    "width": 64,
                    "height": 32,
                    "preview_jpeg": base64.b64encode(self.jpeg).decode(),
                },
            )
        if request.url.path.endswith("/inference/webcam"):
            self.payload = json.loads(request.content)
            return httpx.Response(200, stream=WebcamStream(self))
        return await fixtures.RtspApiTests.handle(self, request)

    def start(self, **fields: object) -> httpx.Response:
        """Tạo webcam run mặc định camera 0 qua cùng model/options live."""
        return self.client.post(
            "/api/v1/runs/webcam",
            json={"model_id": self.model_id, "duration_seconds": 2, **fields},
        )

    def test_direct_device_payload_http_preview_and_json_isolation(self) -> None:
        """AI nhận integer 0; ảnh HTTP không xuất hiện trong DB/JSON/WebSocket hay file."""
        checked = self.client.post(
            "/api/v1/runs/webcam/check", json={"device_index": 0}
        )
        self.assertEqual(checked.status_code, 200)
        response = self.start()
        self.assertEqual(response.status_code, 202, response.text)
        record = self.wait(response.json()["id"])
        self.assertEqual(record["status"], "completed", record)
        self.assertEqual(self.payload["device_index"], 0)
        self.assertNotIn("stream_url", self.payload)
        self.assertNotIn("source_location", self.payload)
        self.assertEqual(record["completion_reason"], "duration_limit")
        self.assertNotIn("preview_jpeg", json.dumps(record))
        frame = self.client.get(f"/api/v1/runs/{record['id']}/preview")
        self.assertEqual(frame.content, self.jpeg)
        self.assertEqual(frame.headers["content-type"], "image/jpeg")
        self.assertFalse(self.app.state.streams.paths)
        self.assertEqual(list(self.app.state.runs.storage.root.iterdir()), [])
        self.assertEqual(self.app.state.sources.repository.count(), 0)

    def test_cancel_releases_device_reservation_and_validates_index(self) -> None:
        """Không chạy hai model cùng webcam; dừng nhả reservation và model lease."""
        self.hold = True
        record = self.start().json()
        for _ in range(100):
            if self.client.get(f"/api/v1/runs/{record['id']}").json().get("result"):
                break
            time.sleep(0.01)
        self.assertEqual(self.start().status_code, 409)
        stopped = self.client.delete(f"/api/v1/runs/{record['id']}").json()
        self.assertEqual(stopped["status"], "cancelled")
        self.assertFalse(self.app.state.runs.tasks)
        self.assertNotIn(self.model_id, self.app.state.models.in_use)
        for value in [-1, 16, True, "0"]:
            self.assertEqual(self.start(device_index=value).status_code, 422)
        self.assertEqual(self.start(stream_url="rtsp://not-allowed").status_code, 422)
