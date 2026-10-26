"""Kiểm thử lượt chạy ảnh với DB/storage thật và AI HTTP giả lập."""

import json
import shutil
import subprocess
import tempfile
import time
import unittest
from collections.abc import AsyncIterator
from contextlib import ExitStack
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import anyio
import httpx
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.core.logs import LogBuffer
from app.main import create_app

CLIENT = httpx.AsyncClient


# ----------------------------- Video kiểm thử --------------------------------
@lru_cache(maxsize=1)
def video_bytes() -> bytes:
    """Tạo MP4 ngắn bằng FFmpeg một lần, chỉ giữ bytes trong bộ nhớ test."""
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "clip.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=160x90:r=10",
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return path.read_bytes()


# ----------------------------- Luồng AI giả lập ------------------------------
class FrameStream(httpx.AsyncByteStream):
    """Phát hai frame và terminal, có thể bỏ terminal để mô phỏng kết nối đứt."""

    def __init__(self, delay: float, partial: bool) -> None:
        """Giữ độ trễ và cờ EOF sớm, không tạo task hoặc mở kết nối."""
        self.delay = delay
        self.partial = partial

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Yield NDJSON từng frame, gồm một frame rỗng để không giữ bbox cũ."""
        result = {
            "sourceSize": {"width": 160, "height": 90},
            "detections": [],
            "classifications": [],
            "device": "cpu",
            "elapsedMs": 100,
        }
        for index in [0, 2]:
            await anyio.sleep(self.delay)
            event = {
                "type": "frame",
                "result": {**result, "frameId": index},
                "progress": {
                    "frames_processed": index // 2 + 1,
                    "frame_index": index,
                    "total_frames": 10,
                    "percent": (index + 1) * 10,
                },
            }
            yield (json.dumps(event) + "\n").encode()
        if not self.partial:
            yield (
                json.dumps(
                    {
                        **event,
                        "type": "completed",
                        "progress": {**event["progress"], "percent": 100},
                    }
                )
                + "\n"
            ).encode()


# ----------------------------- Kiểm thử API chạy -----------------------------
class RunTests(unittest.TestCase):
    """Xác minh ảnh tạm, source đã lưu, huỷ job, model lease và snapshot WebSocket."""

    def setUp(self) -> None:
        """Tạo DB/storage/app riêng, thay mạng AI bằng MockTransport và dọn khi xong."""
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.settings = Settings(
            database_path=root / "db.sqlite3",
            sources_path=root / "sources",
            ai_url="http://ai.test",
        )
        self.video_partial = False
        self.ai_logs = LogBuffer("ai")
        self.inference_headers = []
        self.delay = 0.01
        self.ai_fail = False
        self.stack.enter_context(
            patch("httpx.AsyncClient", side_effect=self.make_client)
        )
        self.app = create_app(self.settings)
        self.client = self.stack.enter_context(TestClient(self.app))
        stream = BytesIO()
        Image.new("RGB", (64, 32), "blue").save(stream, format="PNG")
        self.image = stream.getvalue()
        model = self.client.post(
            "/api/v1/models/upload", files={"file": ("model.pt", b"model")}
        ).json()
        self.model_id = model["id"]
        for _ in range(100):
            if (
                self.client.get(f"/api/v1/models/{self.model_id}").json()["inspection"][
                    "status"
                ]
                == "ready"
            ):
                break
            time.sleep(0.01)

    def make_client(self, **kwargs) -> httpx.AsyncClient:
        """Giữ HTTPX client thật nhưng thay transport, không truy cập Internet."""
        return CLIENT(transport=httpx.MockTransport(self.handle), **kwargs)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        """Mô phỏng inspect và inference với độ trễ/lỗi có kiểm soát."""
        if request.url.path == "/api/v1/logs":
            return httpx.Response(
                200,
                json=self.ai_logs.read(request.url.params.get("after")).model_dump(),
            )
        if "/inference/" in request.url.path:
            self.inference_headers.append(request.headers.get("X-VisionKit-Run-ID"))
        if request.url.path.endswith("inspect"):
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "metadata": {
                        "format": "pt",
                        "family": "yolo",
                        "task": "detect",
                        "names": {"0": "person"},
                    },
                },
            )
        if request.url.path.endswith("/video"):
            return httpx.Response(
                200, stream=FrameStream(self.delay, self.video_partial)
            )
        await anyio.sleep(self.delay)
        if self.ai_fail:
            return httpx.Response(
                422, json={"detail": "Không có GPU CUDA. Hãy chọn CPU."}
            )
        return httpx.Response(
            200,
            json={
                "sourceSize": {"width": 64, "height": 32},
                "detections": [
                    {
                        "classId": 0,
                        "label": "person",
                        "confidence": 0.9,
                        "bbox": [1, 2, 30, 20],
                    }
                ],
                "classifications": [],
                "device": "cpu",
                "elapsedMs": 10,
            },
        )

    def start(self, **kwargs) -> httpx.Response:
        """Tạo lượt chạy ảnh upload, cho phép thay form để kiểm tra trường sai."""
        return self.client.post(
            "/api/v1/runs",
            data={
                "model_id": self.model_id,
                "options": json.dumps({"device": "cpu"}),
                **kwargs,
            },
            files={"file": ("image.png", self.image)},
        )

    def wait(self, run_id: str) -> dict:
        """Poll tối đa hai giây cho trạng thái kết thúc và trả bản ghi chạy."""
        for _ in range(200):
            record = self.client.get(f"/api/v1/runs/{run_id}").json()
            if record["status"] not in {"queued", "running"}:
                return record
            time.sleep(0.01)
        self.fail("Job không kết thúc")

    def test_unsaved_source_result_preview_and_websocket(self) -> None:
        """Ảnh chạy không vào thư viện, kết quả giữ trong DB và có snapshot WS cùng preview."""
        response = self.start()
        self.assertEqual(response.status_code, 202, response.text)
        run = self.wait(response.json()["id"])
        self.assertEqual(run["status"], "completed", run)
        self.assertIn(run["id"], self.inference_headers)
        logs = self.client.get("/api/v1/logs", params={"run_id": run["id"]}).json()[
            "items"
        ]
        self.assertTrue(any("Hoàn tất inference" in entry["message"] for entry in logs))
        self.assertEqual(run["result"]["detections"][0]["label"], "person")
        self.assertEqual(self.client.get("/api/v1/sources").json()["total"], 0)
        self.assertEqual(
            self.client.get(f"/api/v1/runs/{run['id']}/preview").content, self.image
        )
        with self.client.websocket_connect(
            f"/api/v1/runs/{run['id']}/events",
            headers={"origin": "http://localhost:3001"},
        ) as socket:
            self.assertEqual(socket.receive_json()["status"], "completed")
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get(f"/api/v1/runs/{run['id']}").json()["status"], "completed"
            )

    def test_saved_source_runs_without_changing_library(self) -> None:
        """Source đã lưu được snapshot riêng; lượt chạy không thêm nguồn hoặc thay model."""
        source = self.client.post(
            "/api/v1/sources/upload", files={"file": ("saved.png", self.image)}
        ).json()
        response = self.client.post(
            "/api/v1/runs",
            data={
                "model_id": self.model_id,
                "source_id": source["id"],
                "options": "{}",
            },
        )
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(self.wait(response.json()["id"])["status"], "completed")
        self.assertEqual(self.client.get("/api/v1/sources").json()["total"], 1)

    def test_completed_runs_remove_unused_model_counter(self) -> None:
        """Chạy xong không giữ khoá model giá trị 0; giải phóng lặp không ảnh hưởng lượt khác."""
        record = self.wait(self.start().json()["id"])
        self.assertEqual(record["status"], "completed")
        self.assertNotIn(self.model_id, self.app.state.models.in_use)
        self.app.state.runs._release(record["id"])
        self.assertNotIn(self.model_id, self.app.state.models.in_use)

    def test_cancel_and_protect_active_model(self) -> None:
        """Model đang chạy không bị xoá; huỷ giải phóng lease và không ghi kết quả muộn."""
        self.delay = 1
        run = self.start().json()
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{self.model_id}").status_code, 409
        )
        response = self.client.delete(f"/api/v1/runs/{run['id']}")
        self.assertEqual(response.json()["status"], "cancelled")
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{self.model_id}").status_code, 204
        )

    def test_failure_and_validation(self) -> None:
        """AI báo lỗi được giữ nguyên thông báo; form sai/file hỏng không tạo job."""
        self.ai_fail = True
        run = self.wait(self.start().json()["id"])
        self.assertEqual(run["status"], "failed")
        self.assertIn("CUDA", run["error"])
        self.assertEqual(self.start(options='{"conf":2}').status_code, 422)
        self.assertEqual(self.start(options='{"classes":[999]}').status_code, 422)
        self.assertEqual(
            self.client.post(
                "/api/v1/runs",
                data={"model_id": self.model_id, "options": "{}"},
                files={"file": ("bad.png", b"bad")},
            ).status_code,
            415,
        )

    def test_queued_cancel_keeps_other_model_lease(self) -> None:
        """Hai lượt cùng model giữ hai lease; huỷ lượt chờ không cho xoá model đang chạy lượt còn lại."""
        self.delay = 1
        first = self.start().json()
        second = self.start().json()
        self.assertEqual(
            self.client.delete(f"/api/v1/runs/{second['id']}").json()["status"],
            "cancelled",
        )
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{self.model_id}").status_code, 409
        )
        self.client.delete(f"/api/v1/runs/{first['id']}")
        self.assertEqual(
            self.client.delete(f"/api/v1/models/{self.model_id}").status_code, 204
        )

    def test_expired_snapshot_cleanup(self) -> None:
        """Lượt terminal hết hạn xoá snapshot/DB, không thêm hoặc xoá nguồn trong thư viện."""
        record = self.wait(self.start().json()["id"])
        repository = self.app.state.runs.repository
        stored = repository.get(record["id"])
        repository.save(
            stored.model_copy(update={"expires_at": "2000-01-01T00:00:00+00:00"})
        )
        self.assertEqual(
            self.client.get(f"/api/v1/runs/{record['id']}").status_code, 410
        )
        self.app.state.runs.cleanup_expired()
        self.assertIsNone(repository.get(record["id"]))
        self.assertFalse(
            self.app.state.runs.storage.path(record["source_location"]).exists()
        )

    @unittest.skipUnless(shutil.which("ffmpeg"), "Cần FFmpeg")
    def test_video_stream_saved_source_and_range(self) -> None:
        """Video đã lưu tự chọn adapter video; lưu kết quả cuối và preview trả MP4 có HTTP Range."""
        source = self.client.post(
            "/api/v1/sources/upload",
            data={"kind": "video"},
            files={"file": ("clip.mp4", video_bytes())},
        ).json()
        response = self.client.post(
            "/api/v1/runs",
            data={
                "model_id": self.model_id,
                "source_id": source["id"],
                "options": '{"vid_stride":2}',
            },
        )
        self.assertEqual(response.status_code, 202, response.text)
        run = self.wait(response.json()["id"])
        self.assertEqual(run["status"], "completed", run)
        self.assertEqual(run["source_kind"], "video")
        self.assertEqual(run["progress"]["frames_processed"], 2)
        self.assertEqual(run["progress"]["percent"], 100)
        self.assertEqual(run["result"]["frameId"], 2)
        preview = self.client.get(
            f"/api/v1/runs/{run['id']}/preview", headers={"Range": "bytes=0-31"}
        )
        self.assertEqual(preview.status_code, 206)
        self.assertEqual(preview.content, video_bytes()[:32])
        self.assertEqual(preview.headers["content-type"], "video/mp4")

    @unittest.skipUnless(shutil.which("ffmpeg"), "Cần FFmpeg")
    def test_video_partial_stream_is_failed(self) -> None:
        """EOF trước completed không được báo thành công, vẫn giữ frame cuối để chẩn đoán."""
        self.video_partial = True
        response = self.client.post(
            "/api/v1/runs",
            data={"model_id": self.model_id, "kind": "video", "options": "{}"},
            files={"file": ("clip.mp4", video_bytes())},
        )
        self.assertEqual(response.status_code, 202, response.text)
        run = self.wait(response.json()["id"])
        self.assertEqual(run["status"], "failed", run)
        self.assertEqual(run["result"]["frameId"], 2)
        self.assertIn("gián đoạn", run["error"])
        self.assertEqual(self.client.get("/api/v1/sources").json()["total"], 0)
