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

    def __init__(
        self, delay: float, partial: bool, detections: list | None = None
    ) -> None:
        """Giữ độ trễ và cờ EOF sớm, không tạo task hoặc mở kết nối."""
        self.delay = delay
        self.partial = partial
        self.detections = detections or []

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """Yield NDJSON từng frame, gồm một frame rỗng để không giữ bbox cũ."""
        result = {
            "sourceSize": {"width": 160, "height": 90},
            "detections": self.detections,
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
        self.video_detections = []
        self.ai_logs = LogBuffer("ai")
        self.inference_headers = []
        self.inference_payloads = []
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
            self.inference_payloads.append(json.loads(request.content))
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
                200,
                stream=FrameStream(
                    self.delay, self.video_partial, self.video_detections
                ),
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

    def test_yoloe_prompt_snapshot_and_validation(self) -> None:
        """Prompt đi xuyên backend/AI theo thứ tự và còn nguyên sau khi mở lại DB."""
        options = {
            "device": "cpu",
            "text_prompts": [" laptop ", "person", "cell phone"],
        }
        self.assertEqual(self.start(options=json.dumps(options)).status_code, 422)
        model = self.app.state.models.repository.configure(
            self.model_id, "yoloe", "segment"
        )
        response = self.start(options=json.dumps(options))
        self.assertEqual(response.status_code, 202, response.text)
        run = self.wait(response.json()["id"])
        self.assertEqual(run["status"], "completed", run)
        expected = ["laptop", "person", "cell phone"]
        self.assertEqual(run["options"]["text_prompts"], expected)
        self.assertEqual(
            self.inference_payloads[-1]["options"]["text_prompts"], expected
        )
        self.assertEqual(self.inference_payloads[-1]["family"], "yoloe")
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get(f"/api/v1/runs/{run['id']}").json()["options"][
                    "text_prompts"
                ],
                expected,
            )
        for prompts in (
            [],
            ["car", "CAR"],
            ["a" * 81],
            ["a\tb"],
            [str(i) for i in range(81)],
        ):
            self.assertEqual(
                self.start(options=json.dumps({"text_prompts": prompts})).status_code,
                422,
            )
        self.assertEqual(
            self.start(options=json.dumps({**options, "classes": [0]})).status_code, 422
        )
        model.variant.format = "onnx"
        with patch.object(self.app.state.models, "available", return_value=model):
            self.assertEqual(self.start(options=json.dumps(options)).status_code, 422)

    def service_profile(self, *, auto_start: bool = False) -> tuple[str, dict]:
        """Tạo cấu hình video liên tục trong DB test và tạm dừng vòng nền để tick xác định."""
        from uuid import uuid4

        self.app.state.counting_supervisor.paused = True
        self.app.state.models.repository.configure(self.model_id, "yoloe", "segment")
        source = self.client.post(
            "/api/v1/sources/upload",
            data={"kind": "video", "name": "Service video"},
            files={"file": ("clip.mp4", video_bytes())},
        ).json()
        signature = self.client.get(f"/api/v1/counting/sources/{source['id']}").json()[
            "source_signature"
        ]
        body = {
            "name": "Service profile",
            "source_id": source["id"],
            "source_signature": signature,
            "config": {
                "reference_width": 160,
                "reference_height": 90,
                "classes": ["person"],
                "zones": [
                    {
                        "id": str(uuid4()),
                        "name": "A",
                        "classes": ["person"],
                        "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                    }
                ],
            },
            "monitor": {
                "model_id": self.model_id,
                "continuous": True,
                "auto_start": auto_start,
                "duration_seconds": 60,
            },
        }
        response = self.client.post("/api/v1/counting/profiles", json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"], body

    def test_continuous_rollover_stop_and_recoverable_delete(self) -> None:
        """Nối video, dọn snapshot cũ, Dừng bền vững và nhân bản/xoá/hoàn tác không chạy AI."""
        pid, body = self.service_profile()
        endpoint = f"/api/v1/counting/profiles/{pid}"
        run = self.client.post(endpoint + "/runs").json()
        self.wait(run["id"])
        self.client.portal.call(self.app.state.counting_supervisor.tick)
        restarted = self.client.get(endpoint).json()
        self.assertTrue(restarted["enabled"])
        self.assertNotEqual(restarted["current_run_id"], run["id"])
        self.assertEqual(self.client.get(f"/api/v1/runs/{run['id']}").status_code, 404)
        self.assertEqual(self.client.delete(endpoint).status_code, 409)
        copied = self.client.post(endpoint + "/duplicate").json()
        self.assertFalse(copied["enabled"])
        self.assertFalse(copied["monitor"]["auto_start"])
        self.assertIsNone(copied["current_run_id"])
        self.assertEqual(copied["config"], restarted["config"])
        self.assertNotEqual(
            self.client.post(endpoint + "/duplicate").json()["name"], copied["name"]
        )
        stopped = self.client.post(endpoint + "/stop").json()
        self.assertFalse(stopped["enabled"])
        stopped_id = stopped["current_run_id"]
        self.client.portal.call(self.app.state.counting_supervisor.tick)
        self.assertEqual(self.client.get(endpoint).json()["current_run_id"], stopped_id)
        deleted = self.client.delete(endpoint)
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        restored = self.client.post(endpoint + "/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertFalse(restored.json()["enabled"])
        self.assertEqual(restored.json()["name"], body["name"])
        self.assertEqual(
            self.client.put(
                endpoint,
                json={
                    **body,
                    "monitor": {
                        **body["monitor"],
                        "continuous": False,
                        "auto_start": True,
                    },
                },
            ).status_code,
            422,
        )

    def test_continuous_failure_backoff_and_watchdog(self) -> None:
        """Lỗi EOF thử lại có backoff; worker im lặng bị thu hồi, Dừng huỷ cả lần thử kế."""
        from datetime import datetime, timedelta, timezone

        pid, _ = self.service_profile()
        endpoint = f"/api/v1/counting/profiles/{pid}"
        supervisor = self.app.state.counting_supervisor
        clock = [100.0]
        supervisor.clock = lambda: clock[0]
        self.video_partial = True
        initial = self.client.post(endpoint + "/runs").json()
        self.assertEqual(self.wait(initial["id"])["status"], "failed")
        self.client.portal.call(supervisor.tick)
        self.assertEqual(
            self.client.get(endpoint).json()["runtime"]["phase"], "retrying"
        )
        self.client.portal.call(supervisor.tick)
        self.assertEqual(
            self.client.get(endpoint).json()["current_run_id"], initial["id"]
        )
        self.video_partial = False
        self.delay = 10
        clock[0] += 2
        self.client.portal.call(supervisor.tick)
        next_id = self.client.get(endpoint).json()["current_run_id"]
        self.assertNotEqual(next_id, initial["id"])
        time.sleep(0.05)
        old = self.app.state.runs.get(next_id).model_copy(
            update={
                "status": "running",
                "updated_at": (
                    datetime.now(timezone.utc) - timedelta(seconds=60)
                ).isoformat(),
            }
        )
        self.app.state.runs.latest[next_id] = old
        self.client.portal.call(supervisor.tick)
        self.assertEqual(
            self.client.get(endpoint).json()["runtime"]["phase"], "retrying"
        )
        self.assertEqual(
            self.client.get(f"/api/v1/runs/{next_id}").json()["status"], "cancelled"
        )
        self.client.post(endpoint + "/stop")
        clock[0] += 100
        self.client.portal.call(supervisor.tick)
        self.assertFalse(self.client.get(endpoint).json()["enabled"])
        self.assertEqual(self.client.get(endpoint).json()["current_run_id"], next_id)

    def test_service_stop_and_watchdog_reclaim_run_after_source_changes(self) -> None:
        """Nguồn đổi chữ ký vẫn thu hồi được worker cũ dù API không trả con trỏ cũ."""
        pid, body = self.service_profile()
        endpoint = f"/api/v1/counting/profiles/{pid}"
        self.delay = 10
        database = self.app.state.sources.repository.database
        source_id = body["source_id"]
        original_metadata = dict(self.app.state.sources.get(source_id).metadata)
        for supervisor_first in [False, True]:
            with database.connection() as connection:
                connection.execute(
                    "UPDATE sources SET metadata_json=? WHERE id=?",
                    (json.dumps(original_metadata), source_id),
                )
            record = self.client.post(endpoint + "/runs").json()
            with database.connection() as connection:
                connection.execute(
                    "UPDATE sources SET metadata_json=? WHERE id=?",
                    (json.dumps({**original_metadata, "width": 320}), source_id),
                )
            self.assertTrue(self.client.get(endpoint).json()["stale"])
            self.assertIsNone(self.client.get(endpoint).json()["current_run_id"])
            if supervisor_first:
                self.client.portal.call(self.app.state.counting_supervisor.tick)
            self.client.post(endpoint + "/stop")
            self.assertEqual(
                self.client.get(f"/api/v1/runs/{record['id']}").json()["status"],
                "cancelled",
            )
            self.assertFalse(self.client.get(endpoint).json()["enabled"])

    def test_continuous_boot_recovery_and_source_exclusivity(self) -> None:
        """Startup khôi phục ý định bật, giữ Dừng qua restart và chặn hai dịch vụ cùng nguồn."""
        pid, body = self.service_profile(auto_start=True)
        endpoint = f"/api/v1/counting/profiles/{pid}"
        supervisor = self.app.state.counting_supervisor
        self.assertTrue(self.client.get(endpoint).json()["enabled"])
        self.client.portal.call(supervisor.tick)
        original_id = self.client.get(endpoint).json()["current_run_id"]
        self.wait(original_id)
        copy = self.client.post(endpoint + "/duplicate").json()
        conflict = self.client.post(f"/api/v1/counting/profiles/{copy['id']}/runs")
        self.assertEqual(conflict.status_code, 409, conflict.text)
        # Mô phỏng tiến trình backend mới bằng lifespan thật sau khi đóng app cũ.
        self.client.__exit__(None, None, None)
        with TestClient(create_app(self.settings)) as reopened:
            for _ in range(100):
                recovered = reopened.get(endpoint).json()
                if recovered["current_run_id"] != original_id:
                    break
                time.sleep(0.02)
            self.assertTrue(recovered["enabled"])
            self.assertNotEqual(recovered["current_run_id"], original_id)
            reopened.post(endpoint + "/stop")
        with TestClient(create_app(self.settings)) as reopened:
            stopped = reopened.get(endpoint).json()
            self.assertFalse(stopped["enabled"])
            self.assertEqual(stopped["current_run_id"], recovered["current_run_id"])

    def test_named_counting_profiles_are_independent_and_run_saved_snapshot(
        self,
    ) -> None:
        """Hai cấu hình cùng video giữ vùng/ngưỡng/lượt riêng, lưu không sửa run cũ."""
        from uuid import uuid4

        source = self.client.post(
            "/api/v1/sources/upload",
            data={"kind": "video", "name": "Profile video"},
            files={"file": ("clip.mp4", video_bytes())},
        ).json()
        base = "/api/v1/counting/profiles"
        signature = self.client.get(f"/api/v1/counting/sources/{source['id']}").json()[
            "source_signature"
        ]
        body = {
            "name": "  Cấu hình 1  ",
            "source_id": source["id"],
            "source_signature": signature,
            "config": {
                "reference_width": 160,
                "reference_height": 90,
                "classes": ["person"],
                "zones": [
                    {
                        "id": str(uuid4()),
                        "name": "A",
                        "classes": ["person"],
                        "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                    }
                ],
            },
            "monitor": {
                "model_id": self.model_id,
                "options": {"conf": 0.31, "iou": 0.6},
                "duration_seconds": 3600,
            },
        }
        first = self.client.post(base, json=body)
        self.assertEqual(first.status_code, 201, first.text)
        first_id = first.json()["id"]
        self.assertEqual(first.json()["name"], "Cấu hình 1")
        second = self.client.post(base, json={**body, "name": "Cấu hình 2"})
        self.assertEqual(second.status_code, 201, second.text)
        second_id = second.json()["id"]
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(len(self.client.get(base).json()), 2)
        for name in ["", "   ", "x\ny"]:
            self.assertEqual(
                self.client.post(base, json={**body, "name": name}).status_code, 422
            )
        self.assertEqual(
            self.client.post(base, json={**body, "name": "cẤU HÌNH 1"}).status_code, 409
        )
        self.assertEqual(
            self.client.put(
                f"{base}/{second_id}", json={**body, "name": "Cấu hình 1"}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                base, json={**body, "name": "stale", "source_signature": "0" * 64}
            ).status_code,
            409,
        )
        self.assertEqual(self.client.post(f"{base}/{first_id}/runs").status_code, 422)
        self.app.state.models.repository.configure(self.model_id, "yoloe", "segment")
        self.delay = 0.3
        started = self.client.post(f"{base}/{first_id}/runs")
        self.assertEqual(started.status_code, 202, started.text)
        run_id = started.json()["id"]
        self.assertEqual(self.client.post(f"{base}/{second_id}/runs").status_code, 409)
        self.assertIsNone(
            self.client.get(f"{base}/{second_id}").json()["current_run_id"]
        )
        self.assertEqual(
            self.client.get(f"{base}/{first_id}").json()["current_run_id"], run_id
        )
        changed = {
            **body,
            "name": "Cấu hình 1 sửa",
            "monitor": {**body["monitor"], "options": {"conf": 0.8}},
        }
        updated = self.client.put(f"{base}/{first_id}", json=changed)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(
            self.client.get(f"{base}/{second_id}").json()["monitor"]["options"]["conf"],
            0.31,
        )
        self.assertEqual(self.wait(run_id)["options"]["conf"], 0.31)
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get(f"{base}/{first_id}").json()["name"], "Cấu hình 1 sửa"
            )
            self.assertEqual(len(reopened.get(base).json()), 2)
        second_run = self.client.post(f"{base}/{second_id}/runs")
        self.assertEqual(second_run.status_code, 202, second_run.text)
        self.wait(second_run.json()["id"])
        self.assertEqual(
            self.client.get(f"{base}/{first_id}").json()["current_run_id"], run_id
        )
        metadata = dict(self.app.state.sources.get(source["id"]).metadata)
        metadata["width"] = 320
        with self.app.state.sources.repository.database.connection() as connection:
            connection.execute(
                "UPDATE sources SET metadata_json=? WHERE id=?",
                (json.dumps(metadata), source["id"]),
            )
        self.assertTrue(self.client.get(f"{base}/{first_id}").json()["stale"])
        self.assertEqual(self.client.post(f"{base}/{first_id}/runs").status_code, 409)

    def test_counting_video_snapshot_persistence_and_model_validation(self) -> None:
        """Lưu vùng theo nguồn, snapshot run và không gửi cấu hình đếm sang AI."""
        from uuid import uuid4

        from app.modules.counting.schemas import CLASSES

        source = self.client.post(
            "/api/v1/sources/upload",
            data={"kind": "video", "name": "Counting video"},
            files={"file": ("clip.mp4", video_bytes())},
        ).json()
        source_id = source["id"]
        endpoint = f"/api/v1/counting/sources/{source_id}"
        current = self.client.get(endpoint).json()
        self.assertIsNone(current["config"])
        config = {
            "reference_width": 160,
            "reference_height": 90,
            "zones": [
                {
                    "id": str(uuid4()),
                    "name": "Full frame",
                    "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                }
            ],
        }
        payload = {"source_signature": current["source_signature"], "config": config}
        saved = self.client.put(endpoint, json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(
            self.client.get(endpoint).json()["config"]["zones"][0]["name"], "Full frame"
        )
        body = {**payload, "source_id": source_id, "model_id": self.model_id}
        self.assertEqual(
            self.client.post("/api/v1/counting/runs", json=body).status_code, 422
        )
        self.app.state.models.repository.configure(self.model_id, "yoloe", "segment")
        self.video_detections = [
            {"label": "person", "bbox": [10, 10, 40, 80]},
            {"label": "wheelchair", "bbox": [20, 20, 60, 85]},
        ]
        response = self.client.post("/api/v1/counting/runs", json=body)
        self.assertEqual(response.status_code, 202, response.text)
        run_id = response.json()["id"]
        run = self.wait(run_id)
        self.assertEqual(run["status"], "completed", run)
        self.assertTrue(run["counts"]["valid"])
        self.assertEqual(
            run["counts"]["regions"][0]["counts"],
            {**dict.fromkeys(CLASSES, 0), "person": 1, "wheelchair": 1},
        )
        self.assertEqual(
            self.inference_payloads[-1]["options"]["text_prompts"], list(CLASSES)
        )
        self.assertNotIn("counting", self.inference_payloads[-1])
        changed = {**config, "zones": []}
        self.assertEqual(
            self.client.put(endpoint, json={**payload, "config": changed}).status_code,
            200,
        )
        self.assertEqual(
            len(self.client.get(f"/api/v1/runs/{run_id}").json()["counting"]["zones"]),
            1,
        )
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(reopened.get(endpoint).json()["config"]["zones"], [])
            self.assertTrue(
                reopened.get(f"/api/v1/runs/{run_id}").json()["counts"]["valid"]
            )
        self.assertEqual(
            self.client.post(
                "/api/v1/counting/runs", json={**body, "config": changed}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.put(
                endpoint, json={**payload, "source_signature": "a" * 64}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/counting/runs", json={**body, "source_signature": "a" * 64}
            ).status_code,
            409,
        )
        custom = {
            **config,
            "classes": ["laptop", "cell phone"],
            "zones": [{**config["zones"][0], "classes": ["laptop"]}],
        }
        self.assertEqual(
            self.client.put(endpoint, json={**payload, "config": custom}).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(endpoint).json()["config"]["classes"], custom["classes"]
        )
        self.video_detections = [{"label": "laptop", "bbox": [10, 10, 40, 80]}]
        created = self.client.post(
            "/api/v1/counting/runs",
            json={
                **body,
                "config": custom,
                "options": {"text_prompts": ["dog"], "classes": [0]},
            },
        )
        self.assertEqual(created.status_code, 202, created.text)
        custom_run = self.wait(created.json()["id"])
        self.assertEqual(custom_run["status"], "completed", custom_run)
        self.assertEqual(custom_run["counts"]["regions"][0]["counts"], {"laptop": 1})
        self.assertEqual(
            self.inference_payloads[-1]["options"]["text_prompts"], custom["classes"]
        )
        self.assertIsNone(self.inference_payloads[-1]["options"]["classes"])
        self.client.put(endpoint, json={**payload, "config": changed})
        snapshot = self.client.get(f"/api/v1/runs/{custom_run['id']}").json()
        self.assertEqual(snapshot["counting"]["classes"], custom["classes"])
        self.assertEqual(snapshot["counting"]["zones"][0]["classes"], ["laptop"])
        monitor = {
            "model_id": self.model_id,
            "options": {"conf": 0.4, "iou": 0.6, "device": "cpu", "max_fps": 8},
            "duration_seconds": 7200,
        }
        monitored = self.client.put(
            endpoint, json={**payload, "config": custom, "monitor": monitor}
        )
        self.assertEqual(monitored.status_code, 200, monitored.text)
        self.assertEqual(monitored.json()["monitor"]["model_id"], self.model_id)
        self.assertEqual(monitored.json()["monitor"]["options"]["conf"], 0.4)
        self.assertEqual(monitored.json()["current_run_id"], custom_run["id"])
        self.assertEqual(monitored.json()["monitor"]["duration_seconds"], 7200)
        # Luồng cũ chỉ lưu vùng vẫn giữ thiết lập giám sát và ID lượt hiện tại.
        self.client.put(endpoint, json={**payload, "config": changed})
        persisted = self.client.get(endpoint).json()
        self.assertEqual(persisted["monitor"], monitored.json()["monitor"])
        self.assertEqual(persisted["current_run_id"], custom_run["id"])
        with TestClient(create_app(self.settings)) as reopened:
            self.assertEqual(
                reopened.get(endpoint).json()["monitor"], persisted["monitor"]
            )
        for seconds in (0, 61, 14460):
            invalid = self.client.put(
                endpoint,
                json={**payload, "monitor": {**monitor, "duration_seconds": seconds}},
            )
            self.assertEqual(invalid.status_code, 422, invalid.text)
        self.assertEqual(
            self.client.get(endpoint).json()["monitor"], persisted["monitor"]
        )
        # Đổi tên không đổi hệ toạ độ; thay nội dung nguồn làm cấu hình cũ hết hiệu lực.
        self.client.patch(f"/api/v1/sources/{source_id}", json={"name": "Renamed"})
        self.assertEqual(
            self.client.get(endpoint).json()["source_signature"],
            current["source_signature"],
        )
        database = self.app.state.sources.repository.database
        with database.connection() as connection:
            connection.execute(
                "UPDATE sources SET location=? WHERE id=?", ("changed.mp4", source_id)
            )
        self.assertTrue(self.client.get(endpoint).json()["stale"])
        self.assertIsNone(self.client.get(endpoint).json()["config"])
        self.assertIsNone(self.client.get(endpoint).json()["monitor"])
        self.assertIsNone(self.client.get(endpoint).json()["current_run_id"])

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
