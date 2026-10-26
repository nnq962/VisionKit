"""Kiểm thử chuẩn hoá kết quả thật và hàng rào đường dẫn/restricted loading cho inference."""

import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from ultralytics.engine.results import Results

from app.adapters.ultralytics.results import serialize_result
from app.contracts.prediction import PredictRequest
from app.core.config import Settings
from app.inference.service import InferenceService
from tests.inspection.test_inspection import ForbiddenPayload


# --------------------------- Kiểm thử kết quả AI -----------------------------
class ResultTests(unittest.TestCase):
    """Đọc tensor Ultralytics thật để đảm bảo bbox/keypoint giữ đúng toạ độ gốc."""

    def test_boxes_pose_and_empty(self) -> None:
        """Chuẩn hoá box/keypoint/confidence theo orig_shape; ảnh rỗng trả detections rỗng."""
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        result = Results(
            image,
            path="image.png",
            names={0: "person"},
            boxes=torch.tensor([[10, 20, 80, 90, 0.9, 0]]),
            keypoints=torch.tensor([[[20, 30, 0.8], [40, 50, 0.1]]]),
        )
        data = serialize_result(result, "cpu", 0.5)
        self.assertEqual(data["sourceSize"], {"width": 200, "height": 100})
        self.assertEqual(data["detections"][0]["bbox"], [10, 20, 80, 90])
        self.assertAlmostEqual(
            data["detections"][0]["keypoints"][0]["confidence"], 0.8, places=5
        )
        empty = Results(
            image, path="image.png", names={0: "person"}, boxes=torch.empty((0, 6))
        )
        self.assertEqual(serialize_result(empty, "cpu", 0.1)["detections"], [])

    def test_classification(self) -> None:
        """Model phân loại trả bảng class/xác suất, không tạo bbox giả."""
        result = Results(
            np.zeros((32, 32, 3), dtype=np.uint8),
            path="x",
            names={0: "a", 1: "b"},
            probs=torch.tensor([0.2, 0.8]),
        )
        data = serialize_result(result, "cpu", 0.1)
        self.assertEqual(data["detections"], [])
        self.assertEqual(data["classifications"][0]["label"], "b")


# --------------------------- Kiểm thử worker ảnh -----------------------------
class InferenceSafetyTests(unittest.IsolatedAsyncioTestCase):
    """Worker chỉ đọc storage cho phép và không fallback unpickle tuỳ ý khi chạy model."""

    async def test_paths_and_restricted_inference(self) -> None:
        """Từ chối path escape và checkpoint chứa callable lạ; không tạo marker tác dụng phụ."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "models"
            models.mkdir()
            runs = root / "runs"
            runs.mkdir()
            image = runs / "image.png"
            Image.new("RGB", (32, 32)).save(image)
            marker = root / "marker"
            model = models / "bad.pt"
            torch.save({"model": ForbiddenPayload(marker)}, model)
            request = PredictRequest(
                model_location=model.name,
                model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                source_location=image.name,
                source_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
            )
            service = InferenceService(Settings(models_path=models, runs_path=runs))
            with self.assertRaises(ValueError):
                await service.predict(
                    request.model_copy(update={"source_location": "../outside.png"})
                )
            with self.assertRaises(ValueError):
                await service.predict(request)
            self.assertFalse(marker.exists())
