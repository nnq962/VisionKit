"""Kiểm tra prompt theo run và nạp encoder local không tải mạng."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from app.adapters.ultralytics.yoloe import configure_text_prompts
from app.contracts.options import PredictOptions
from app.contracts.prediction import ModelPredictRequest


# ----------------------------- Hợp đồng prompt -------------------------------
class TextPromptTests(unittest.TestCase):
    """Bảo vệ thứ tự class và giới hạn đầu vào trước khi worker nạp model."""

    def test_validation_and_order(self) -> None:
        """Giữ thứ tự, cắt khoảng trắng và từ chối cấu hình mơ hồ hoặc quá lớn."""
        options = PredictOptions(text_prompts=[" laptop ", "person", "cell phone"])
        self.assertEqual(options.text_prompts, ["laptop", "person", "cell phone"])
        for prompts in (
            [],
            [" "],
            ["car", "CAR"],
            ["a" * 81],
            ["a\tb"],
            [str(i) for i in range(81)],
        ):
            with self.assertRaises(ValidationError):
                PredictOptions(text_prompts=prompts)
        base = {
            "model_location": "model.pt",
            "model_sha256": "a" * 64,
            "options": options,
        }
        with self.assertRaises(ValidationError):
            ModelPredictRequest(**base)
        request = ModelPredictRequest(**base, family="yoloe", task="segment")
        self.assertEqual(request.options.text_prompts, options.text_prompts)
        with self.assertRaises(ValidationError):
            ModelPredictRequest(
                **{**base, "options": {"text_prompts": ["person"], "classes": [0]}},
                family="yoloe",
            )

    def test_missing_encoder_and_incompatible_head(self) -> None:
        """Thiếu asset hoặc head prompt-free trả lỗi trước khi gọi thư viện encoder."""
        model = SimpleNamespace(
            model=SimpleNamespace(model=[SimpleNamespace(lrpc=True)])
        )
        with self.assertRaisesRegex(ValueError, "prompt-free"):
            configure_text_prompts(model, ["person"], "cpu")
        model.model.model = [SimpleNamespace()]
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch(
                "app.adapters.ultralytics.yoloe.encoder_directory",
                return_value=Path(temporary),
            ),
            self.assertRaisesRegex(ValueError, "Thiếu text encoder"),
        ):
            configure_text_prompts(model, ["person"], "cpu")

    def test_embeddings_are_applied_once_and_encoder_is_released(self) -> None:
        """Dùng encoder local, gán embedding đúng thứ tự và không giữ encoder khi predict."""
        model = MagicMock()
        model.model.model = [SimpleNamespace(is_fused=False)]
        model.model.text_model = "mobileclip2:b"
        prompts = ["cell phone", "person"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "mobileclip2_b.ts"
            path.touch()
            with (
                patch(
                    "app.adapters.ultralytics.yoloe.encoder_directory",
                    return_value=root,
                ),
                patch("ultralytics.nn.text_model.MobileCLIPTS") as encoder,
            ):
                configure_text_prompts(model, prompts, "cpu")
                encoder.assert_called_once_with(device="cpu", weight=str(path))
                model.model.get_text_pe.assert_called_once_with(
                    prompts, cache_clip_model=True
                )
                model.set_classes.assert_called_once_with(
                    prompts, model.model.get_text_pe.return_value
                )
                self.assertNotIn("clip_model", model.model.__dict__)
