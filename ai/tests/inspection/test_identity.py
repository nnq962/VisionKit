"""Kiểm thử định danh nhúng và các trường hợp thiếu/mơ hồ, không suy đoán theo tên upload."""

import unittest

from app.inspection.identity import model_identity


# -------------------------- Kiểm thử dòng model ------------------------------
class ModelIdentityTests(unittest.TestCase):
    """Xác minh chuẩn hoá dòng/scale độc lập phiên bản Ultralytics và task."""

    def test_known_embedded_identifiers(self) -> None:
        """Đọc YOLO26/11/v8 và YOLOE từ YAML hoặc mô tả nhúng, chuẩn hoá scale chữ thường."""
        for value, family, expected in [
            ("yolo26n.yaml", "yolo", ("YOLO26", "n")),
            ("/config/yolo11x-seg.yaml", "yolo", ("YOLO11", "x")),
            ("Ultralytics YOLOv8s model", "yolo", ("YOLOv8", "s")),
            ("Ultralytics YOLOE-26L model", "yoloe", ("YOLOE-26", "l")),
            ("YOLO26", "yolo", ("YOLO26", None)),
        ]:
            self.assertEqual(model_identity(value, family), expected)

    def test_missing_conflicting_or_unrelated_values(self) -> None:
        """Thiếu metadata, chuỗi lạ hoặc khai báo mâu thuẫn không được biến thành kết quả chắc chắn."""
        for value, family in [
            (None, "yolo"),
            ("best.pt", "yolo"),
            ("8.3.222", "yolo"),
            ("notyolo26n.yaml", "yolo"),
            ("yolo26n.yaml", None),
            ("yoloe-26n.yaml", "yolo"),
            ("YOLO11n and YOLO26n", "yolo"),
        ]:
            self.assertEqual(model_identity(value, family), (None, None))
