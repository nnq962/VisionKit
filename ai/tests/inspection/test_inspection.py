"""Kiểm thử metadata PT/ONNX thật, giới hạn đường dẫn và restricted loading."""

import hashlib
import tempfile
import unittest
from pathlib import Path

import onnx
from fastapi.testclient import TestClient
from onnx import TensorProto, helper

from app.contracts.model import InspectRequest
from app.core.config import Settings
from app.inspection.service import InspectionService
from app.main import create_app


# ------------------------------ Payload bị cấm -------------------------------
class ForbiddenPayload:
    """Payload ghi marker nếu bị unpickle không hạn chế; test phải chứng minh nó bị chặn."""

    def __init__(self, marker: Path) -> None:
        """Giữ đường dẫn marker tạm, không ghi file hoặc thực thi lệnh."""
        self.marker = str(marker)

    def __reduce__(self):
        """Mã hoá callable eval bị cấm trong checkpoint, không tự thực thi tại đây."""
        return eval, (
            f"__import__('pathlib').Path({self.marker!r}).write_text('executed')",
        )


# ------------------------------ Tạo ONNX kiểm thử -----------------------------
def make_onnx(path: Path, with_metadata: bool = True) -> None:
    """Ghi graph Identity với shape và metadata mẫu; không cần ONNX Runtime hoặc tải mạng."""
    graph = helper.make_graph(
        [helper.make_node("Identity", ["images"], ["output"])],
        "test",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 640, 640])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3, 640, 640])],
    )
    model = helper.make_model(graph, producer_name="fixture")
    if with_metadata:
        helper.set_model_props(
            model,
            {
                "description": "Ultralytics YOLO11n model",
                "task": "detect",
                "names": "{0:'person',1:'car'}",
                "imgsz": "[640,640]",
                "stride": "32",
            },
        )
    onnx.save(model, path)


# ------------------------------ Kiểm thử inspect -----------------------------
class InspectionTests(unittest.IsolatedAsyncioTestCase):
    """Chạy worker thật trong thư mục tạm và kiểm tra API không cần GPU/inference."""

    @classmethod
    def setUpClass(cls) -> None:
        """Tạo checkpoint Ultralytics nhỏ trên CPU cho các test, tự dọn cuối class."""
        import torch
        from ultralytics.nn.tasks import DetectionModel

        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        torch.set_num_threads(1)
        model = DetectionModel("yolo11n.yaml", nc=2, verbose=False)
        model.names = {0: "person", 1: "car"}
        cls.pt = cls.root / "renamed-checkpoint.pt"
        torch.save(
            {
                "model": model,
                "train_args": {"task": "detect", "imgsz": 640},
                "version": "fixture",
            },
            cls.pt,
        )

    async def inspect(self, path: Path):
        """Gửi đường dẫn tương đối và checksum chính xác đến InspectionService với root tạm."""
        return await InspectionService(Settings(models_path=self.root)).inspect(
            InspectRequest(
                location=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            )
        )

    async def test_pt_metadata_without_filename_guess(self) -> None:
        """Tên file tuỳ ý vẫn nhận YOLO/task/classes/imgsz/stride từ checkpoint thật."""
        result = await self.inspect(self.pt)
        self.assertEqual(result.status, "ready", result)
        self.assertEqual(result.metadata.family, "yolo")
        self.assertEqual(result.metadata.task, "detect")
        self.assertEqual(result.metadata.class_count, 2)
        self.assertEqual(result.metadata.names["1"], "car")
        self.assertEqual(result.metadata.imgsz, [640, 640])
        self.assertEqual(result.metadata.stride, 32)

    async def test_onnx_metadata_and_shape(self) -> None:
        """ONNX có metadata nhận đúng class/task/shape mà không chạy graph."""
        path = self.root / "custom.onnx"
        make_onnx(path)
        result = await self.inspect(path)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.metadata.input_shape, [1, 3, 640, 640])
        self.assertEqual(result.metadata.names, {"0": "person", "1": "car"})

    async def test_onnx_without_metadata_needs_input(self) -> None:
        """Graph ONNX hợp lệ nhưng thiếu family/task trả needs_input, không tự đoán YOLO."""
        path = self.root / "yolo-by-name-only.onnx"
        make_onnx(path, False)
        result = await self.inspect(path)
        self.assertEqual(result.status, "needs_input")
        self.assertIsNone(result.metadata.family)
        self.assertIsNone(result.metadata.task)
        self.assertEqual(result.metadata.input_shape, [1, 3, 640, 640])

    async def test_corrupt_files_and_checksum(self) -> None:
        """File hỏng hoặc checksum không khớp không được đánh dấu metadata ready."""
        for suffix in ("pt", "onnx"):
            path = self.root / f"broken.{suffix}"
            path.write_bytes(b"invalid file")
            self.assertEqual((await self.inspect(path)).status, "failed")
        result = await InspectionService(Settings(models_path=self.root)).inspect(
            InspectRequest(location=self.pt.name, sha256="0" * 64)
        )
        self.assertEqual(result.status, "failed")

    async def test_restricted_loader_blocks_code(self) -> None:
        """Checkpoint chứa eval bị chặn; marker không được ghi và không fallback unsafe."""
        import torch

        marker = self.root / "should-not-exist"
        path = self.root / "untrusted.pt"
        torch.save({"model": ForbiddenPayload(marker)}, path)
        self.assertEqual((await self.inspect(path)).status, "failed")
        self.assertFalse(marker.exists())

    async def test_paths_and_timeout(self) -> None:
        """Từ chối path escape/symlink và kết thúc worker khi quá timeout."""
        service = InspectionService(Settings(models_path=self.root))
        for location in ("../outside.pt", str(self.pt.resolve())):
            result = await service.inspect(
                InspectRequest(location=location, sha256="0" * 64)
            )
            self.assertEqual(result.status, "failed")
        link = self.root / "link.pt"
        link.symlink_to(self.pt)
        self.assertEqual(
            (
                await service.inspect(
                    InspectRequest(location=link.name, sha256="0" * 64)
                )
            ).status,
            "failed",
        )
        service = InspectionService(
            Settings(models_path=self.root, inspect_timeout=0.001)
        )
        result = await service.inspect(
            InspectRequest(
                location=self.pt.name,
                sha256=hashlib.sha256(self.pt.read_bytes()).hexdigest(),
            )
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("thời gian", result.message)

    def test_http_health_and_input_validation(self) -> None:
        """API health không load model; hợp đồng request từ chối checksum hoặc trường sai."""
        with TestClient(create_app(Settings(models_path=self.root))) as client:
            self.assertEqual(client.get("/api/v1/health").json(), {"status": "ok"})
            self.assertEqual(
                client.post(
                    "/api/v1/models/inspect", json={"location": "a.pt", "sha256": "bad"}
                ).status_code,
                422,
            )
