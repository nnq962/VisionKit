"""Kiểm thử RTSP API với SQLite thật và luồng HTTP AI có kiểm soát."""

import json
import time
import unittest
from collections.abc import AsyncIterator
from uuid import uuid4

import anyio
import httpx

from tests.runs import test_api as fixtures


# --------------------------- Luồng AI kiểm thử -------------------------------
class LiveStream(httpx.AsyncByteStream):
    """Gửi frame đầu rồi đợi cancel hoặc terminal; theo dõi đóng HTTP stream."""

    def __init__(self, owner: "RtspApiTests") -> None:
        """Lưu fixture điều khiển chế độ kết thúc và lỗi."""
        self.owner = owner

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Trả NDJSON latest frame và progress live không có percent/total_frames."""
        result = {
            "sourceSize": {"width": 64, "height": 32},
            "detections": [],
            "classifications": [],
            "device": "cpu",
            "elapsedMs": 10,
            "speed": {"inference": 2},
            "frameId": 7,
            "timestampMs": 100,
        }
        event = {
            "type": "frame",
            "result": result,
            "progress": {
                "frames_processed": 1,
                "frame_index": 7,
                "total_frames": None,
                "percent": None,
                "source_fps": 24,
                "processing_fps": 10,
                "is_live": True,
            },
        }
        yield (json.dumps(event) + "\n").encode()
        if self.owner.hold:
            await anyio.sleep(60)
        if self.owner.live_error:
            yield (
                json.dumps({"type": "error", "error": self.owner.url}) + "\n"
            ).encode()
        elif not self.owner.early_eof:
            yield (
                json.dumps({**event, "type": "completed", "reason": "duration_limit"})
                + "\n"
            ).encode()

    async def aclose(self) -> None:
        """Ghi nhận hủy hoặc hoàn tất đều đóng stream HTTP."""
        self.owner.closed += 1


# -------------------------- Kiểm thử API camera ------------------------------
class RtspApiTests(unittest.TestCase):
    """Tạo/sửa nguồn, chạy/huỷ, lease, restart và không rò credential ra JSON/log."""

    setUp = fixtures.RunTests.setUp
    make_client = fixtures.RunTests.make_client
    wait = fixtures.RunTests.wait
    hold = False
    live_error = False
    early_eof = False
    closed = 0
    url = "rtsp://operator:very-private@192.168.1.10:554/live?token=also-private"

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """Chặn endpoint stream riêng; giữ mock inspect/logs và ảnh/video hiện có."""
        if request.url.path.endswith("/inference/stream"):
            self.payload = json.loads(request.content)
            self.run_header = request.headers.get("X-VisionKit-Run-ID")
            return httpx.Response(200, stream=LiveStream(self))
        return await fixtures.RunTests.handle(self, request)

    def source(self) -> dict:
        """Tạo nguồn RTSP chưa mở kết nối và trả response đã che credential."""
        response = self.client.post(
            "/api/v1/sources/rtsp", json={"name": " Camera A ", "url": self.url}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def start_stream(self, source_id: str, **kwargs: object) -> httpx.Response:
        """Tạo live run bằng JSON source/model/options, không gửi URL trong run request."""
        return self.client.post(
            "/api/v1/runs/stream",
            json={
                "source_id": source_id,
                "model_id": self.model_id,
                "options": {"device": "cpu"},
                "duration_seconds": 3,
                **kwargs,
            },
        )

    def test_source_crud_redaction_and_no_files(self) -> None:
        """Tạo/list/get/sửa/rename/xóa source đều che password/query và không tạo media file."""
        source = self.source()
        sid = source["id"]
        self.assertEqual(source["kind"], "stream")
        self.assertEqual(source["name"], "Camera A")
        self.assertEqual(source["location"], "rtsp://192.168.1.10:554/live")
        self.assertIsNone(source["content_url"])
        self.assertIsNone(source["preview_url"])
        stored = self.app.state.sources.get(sid)
        self.assertEqual(stored.location, self.url)
        for path in ["/api/v1/sources?kind=stream", f"/api/v1/sources/{sid}"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("very-private", response.text)
            self.assertNotIn("also-private", response.text)
        for suffix in ["content", "preview"]:
            self.assertEqual(
                self.client.get(f"/api/v1/sources/{sid}/{suffix}").status_code, 404
            )
        updated = self.client.put(
            f"/api/v1/sources/{sid}/rtsp",
            json={
                "name": "Camera B",
                "url": "rtsps://admin:another-private@camera-b/live",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["location"], "rtsps://camera-b/live")
        renamed = self.client.patch(f"/api/v1/sources/{sid}", json={"name": "Renamed"})
        self.assertEqual(renamed.json()["name"], "Renamed")
        self.assertNotIn("another-private", renamed.text)
        self.assertEqual(self.client.delete(f"/api/v1/sources/{sid}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/v1/sources/{sid}").status_code, 404)
        self.assertEqual(list(self.settings.sources_path.iterdir()), [])

    def test_validation_never_echoes_secrets(self) -> None:
        """Sai protocol/port/control, trường lạ hoặc kiểu URL đều trả 422 không lộ input."""
        bodies = [
            {"name": "Camera", "url": url}
            for url in [
                "http://operator:very-private@host/live",
                "rtsp://host:99999/live?secret=very-private",
                "rtsp://host:invalid/live?secret=very-private",
                "rtsp://host/live\nvery-private",
                "rtsp:///very-private",
                "rtsp://host/live#very-private",
            ]
        ]
        bodies += [
            {"name": "Camera", "url": {"password": "very-private"}},
            {"name": "Camera", "url": self.url, "password": "very-private"},
            {"name": "", "url": self.url},
        ]
        for body in bodies:
            response = self.client.post("/api/v1/sources/rtsp", json=body)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertNotIn("very-private", response.text)
        self.assertEqual(self.client.get("/api/v1/sources").json()["total"], 0)

    def test_stream_routes_to_ai_preserves_latest_and_cleans_lease(self) -> None:
        """Snapshot không có URL, AI nhận URL gốc qua POST và live không cần file preview."""
        source = self.source()
        response = self.start_stream(source["id"])
        self.assertEqual(response.status_code, 202, response.text)
        record = self.wait(response.json()["id"])
        self.assertEqual(record["status"], "completed", record)
        self.assertEqual(record["completion_reason"], "duration_limit")
        self.assertEqual(record["source_kind"], "stream")
        self.assertEqual(record["source_location"], "")
        self.assertFalse(record["source_metadata"]["preview_available"])
        self.assertIsNone(record["progress"]["percent"])
        self.assertEqual(record["result"]["frameId"], 7)
        self.assertEqual(self.payload["stream_url"], self.url)
        self.assertNotIn("source_location", self.payload)
        self.assertNotIn("source_sha256", self.payload)
        self.assertEqual(self.run_header, record["id"])
        self.assertEqual(self.payload["duration_seconds"], 3)
        self.assertNotIn("very-private", json.dumps(record))
        self.assertNotIn(self.model_id, self.app.state.models.in_use)
        self.assertFalse(self.app.state.runs.tasks)
        self.assertEqual(
            self.client.get(f"/api/v1/runs/{record['id']}/preview").status_code, 404
        )
        with self.client.websocket_connect(
            f"/api/v1/runs/{record['id']}/events",
            headers={"origin": "http://localhost:3001"},
        ) as socket:
            self.assertEqual(socket.receive_json()["source_kind"], "stream")
        self.assertGreater(self.closed, 0)

    def test_live_cancel_keeps_snapshot_url_after_source_edit_delete(self) -> None:
        """Sửa/xoá camera không đổi URL job đang chạy; cancel nhả task/lease và stream."""
        self.hold = True
        source = self.source()
        record = self.start_stream(source["id"]).json()
        for _ in range(100):
            current = self.client.get(f"/api/v1/runs/{record['id']}").json()
            if current["result"]:
                break
            time.sleep(0.01)
        self.assertIsNotNone(current["result"])
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{self.model_id}").status_code, 409
        )
        self.client.put(
            f"/api/v1/sources/{source['id']}/rtsp",
            json={"name": "New", "url": "rtsp://other/live"},
        )
        self.client.delete(f"/api/v1/sources/{source['id']}")
        self.assertEqual(self.payload["stream_url"], self.url)
        stopped = self.client.delete(f"/api/v1/runs/{record['id']}").json()
        self.assertEqual(stopped["status"], "cancelled")
        self.assertEqual(stopped["result"]["frameId"], 7)
        self.assertFalse(self.app.state.runs.tasks)
        self.assertNotIn(self.model_id, self.app.state.models.in_use)
        self.assertGreater(self.closed, 0)

    def test_failure_and_early_eof_are_not_completed(self) -> None:
        """Mất camera/AI không terminal giữ frame cuối và fail, không phản chiếu URL lỗi."""
        source = self.source()
        for mode in ["live_error", "early_eof"]:
            setattr(self, mode, True)
            record = self.wait(self.start_stream(source["id"]).json()["id"])
            self.assertEqual(record["status"], "failed", record)
            self.assertEqual(record["result"]["frameId"], 7)
            self.assertNotIn("very-private", json.dumps(record))
            self.assertNotIn("very-private", self.client.get("/api/v1/logs").text)
            setattr(self, mode, False)
        self.assertNotIn(self.model_id, self.app.state.models.in_use)

    def test_invalid_run_source_options_duration_and_missing_source(self) -> None:
        """Không chạy file qua stream API, không nhận URL trực tiếp hoặc cấu hình ngoài giới hạn."""
        source = self.source()
        for value in [0, 14401, True, 1.5]:
            self.assertEqual(
                self.start_stream(source["id"], duration_seconds=value).status_code, 422
            )
        self.assertEqual(self.start_stream(str(uuid4())).status_code, 404)
        self.assertEqual(
            self.start_stream(source["id"], stream_url=self.url).status_code, 422
        )
        self.assertEqual(
            self.start_stream(source["id"], options={"imgsz": [1, 1]}).status_code, 422
        )
        self.assertEqual(
            self.start_stream(source["id"], options={"classes": [999]}).status_code, 422
        )
        file_source = self.client.post(
            "/api/v1/sources/upload", files={"file": ("x.png", self.image)}
        ).json()
        self.assertEqual(self.start_stream(file_source["id"]).status_code, 422)
        self.assertEqual(
            self.client.put(
                f"/api/v1/sources/{file_source['id']}/rtsp",
                json={"name": "X", "url": self.url},
            ).status_code,
            422,
        )

    def test_expiry_and_interruption_do_not_touch_source_files(self) -> None:
        """Dọn live record không coi URL/ID là path; interrupt restart đánh dấu failed."""
        source = self.source()
        record = self.wait(self.start_stream(source["id"]).json()["id"])
        repository = self.app.state.runs.repository
        stored = repository.get(record["id"])
        repository.save(
            stored.model_copy(update={"expires_at": "2000-01-01T00:00:00+00:00"})
        )
        self.app.state.runs.cleanup_expired()
        self.assertIsNone(repository.get(record["id"]))
        self.assertEqual(
            self.client.get(f"/api/v1/sources/{source['id']}").status_code, 200
        )
        repository.save(stored.model_copy(update={"status": "running"}))
        repository.interrupt()
        self.assertEqual(repository.get(record["id"]).status, "failed")

    def test_stream_queue_limit_and_queued_cancel_release_each_lease(self) -> None:
        """Bốn live job dùng hàng chờ chung; huỷ job chờ không nhả lease của job đang chạy."""
        self.hold = True
        source = self.source()
        records = [self.start_stream(source["id"]).json() for _ in range(4)]
        self.assertEqual(self.start_stream(source["id"]).status_code, 429)
        self.assertEqual(self.app.state.models.in_use[self.model_id], 4)
        self.client.delete(f"/api/v1/runs/{records[1]['id']}")
        self.assertEqual(self.app.state.models.in_use[self.model_id], 3)
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{self.model_id}").status_code, 409
        )
        for record in records:
            self.client.delete(f"/api/v1/runs/{record['id']}")
        self.assertFalse(self.app.state.runs.tasks)
        self.assertFalse(self.app.state.runs.pinned)
        self.assertNotIn(self.model_id, self.app.state.models.in_use)
