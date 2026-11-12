"""Kiểm thử lựa chọn class ID và text prompt cho từng loại model đếm vùng."""

import unittest

from app.core.errors import SourceError
from app.modules.counting.model_options import counting_options
from app.modules.counting.schemas import CountingConfig
from app.modules.models.schemas import StoredModel
from app.modules.runs.schemas import RunOptions


# ------------------------ Kiểm thử class theo model --------------------------
class CountingModelTests(unittest.TestCase):
    """Giữ hợp đồng YOLOE cũ và kiểm tra nhãn cố định của YOLO PT/ONNX."""

    def model(self, family: str = "yolo", format: str = "pt") -> StoredModel:
        """Tạo metadata model giả lập; không tải weights hoặc ghi thư viện thật."""
        return StoredModel.model_validate(
            {
                "id": "test",
                "location": "test.pt",
                "size_bytes": 1,
                "sha256": "a" * 64,
                "saved_at": "2026-11-12T00:00:00Z",
                "variant": {
                    "id": "test",
                    "familyId": family,
                    "familyName": family,
                    "filename": f"test.{format}",
                    "format": format,
                    "task": "detect",
                },
                "inspection": {
                    "status": "ready",
                    "metadata": {
                        "format": format,
                        "family": family,
                        "names": {"0": "person", "7": "truck"},
                    },
                },
            }
        )

    def test_yolo_fixed_labels_map_to_sparse_ids_without_mutating_options(self) -> None:
        """YOLO PT/ONNX dùng ID metadata và xoá prompt trong bản sao options."""
        config = CountingConfig(
            reference_width=100, reference_height=100, classes=["truck"]
        )
        original = RunOptions(text_prompts=["wheelchair"], classes=[0], conf=0.4)
        for format in ("pt", "onnx"):
            with self.subTest(format=format):
                result = counting_options(self.model(format=format), config, original)
                self.assertEqual(result.classes, [7])
                self.assertIsNone(result.text_prompts)
                self.assertEqual(result.conf, 0.4)
        self.assertEqual(original.text_prompts, ["wheelchair"])
        self.assertEqual(original.classes, [0])

    def test_regular_yolo_supports_all_labels_above_prompt_limit(self) -> None:
        """YOLO dùng đủ nhãn metadata trên 80 class; YOLOE vẫn giới hạn 80 prompt."""
        model = self.model()
        names = {str(index): f"class_{index}" for index in range(100)}
        model.inspection.metadata.names = names
        config = CountingConfig(
            reference_width=1, reference_height=1, classes=list(names.values())
        )
        result = counting_options(model, config, RunOptions())
        self.assertEqual(result.classes, list(range(100)))
        with self.assertRaises(SourceError):
            counting_options(self.model("yoloe"), config, RunOptions())

    def test_yoloe_keeps_custom_prompts_and_requires_pt(self) -> None:
        """YOLOE PT giữ nhãn tự nhập, xoá lọc ID và từ chối ONNX."""
        config = CountingConfig(
            reference_width=100, reference_height=100, classes=["wheelchair"]
        )
        result = counting_options(self.model("yoloe"), config, RunOptions(classes=[0]))
        self.assertEqual(result.text_prompts, ["wheelchair"])
        self.assertIsNone(result.classes)
        with self.assertRaises(SourceError):
            counting_options(self.model("yoloe", "onnx"), config, RunOptions())

    def test_yolo_rejects_unknown_labels_missing_metadata_and_wrong_task(self) -> None:
        """Không biến tên nhập tay hoặc model classify thành lượt đếm hợp lệ."""
        model = self.model()
        config = CountingConfig(
            reference_width=100, reference_height=100, classes=["wheelchair"]
        )
        with self.assertRaises(SourceError):
            counting_options(model, config, RunOptions())
        config.classes = ["person"]
        model.inspection.metadata = None
        with self.assertRaises(SourceError):
            counting_options(model, config, RunOptions())
        model = self.model()
        model.variant.task = "classify"
        with self.assertRaises(SourceError):
            counting_options(model, config, RunOptions())
