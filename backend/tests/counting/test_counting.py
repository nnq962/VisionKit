"""Kiểm tra polygon, điểm neo, vùng chồng nhau và dữ liệu trống/mất hiệu lực."""

import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.modules.counting.geometry import contains
from app.modules.counting.schemas import CLASSES, CountingConfig, CountingZone
from app.modules.counting.service import count_frame


# ----------------------------- Kiểm thử vùng đếm -----------------------------
class CountingTests(unittest.TestCase):
    """Xác minh phép đếm độc lập frame, chuẩn hoá, biên polygon và snapshot lớp."""

    def zone(self, points: list, **kwargs) -> CountingZone:
        """Tạo vùng UUID riêng với class mặc định để tránh trùng ID giữa các test."""
        return CountingZone(id=uuid4(), name="Vùng A", points=points, **kwargs)

    def test_geometry_and_invalid_polygons(self) -> None:
        """Chấp nhận polygon lõm và điểm biên; từ chối tự cắt/đỉnh trùng/toạ độ xấu."""
        polygon = [(0, 0), (1, 0), (1, 0.4), (0.4, 0.4), (0.4, 1), (0, 1)]
        zone = self.zone(polygon)
        self.assertTrue(contains(zone.points, (0.1, 0.9)))
        self.assertFalse(contains(zone.points, (0.8, 0.8)))
        self.assertTrue(contains(zone.points, (0.4, 0.4)))
        for points in [
            [],
            [(0, 0), (1, 1), (0, 1), (1, 0)],
            [(0, 0), (1, 0), (0, 0)],
            [(0, 0), (0.5, 0), (1, 0)],
            [(-0.1, 0), (1, 0), (1, 1)],
            [(0, 0), (float("nan"), 0), (1, 1)],
            [(0, 0), (1, 0), (0.5, 0), (1, 1), (0, 1)],
        ]:
            with self.assertRaises(ValidationError):
                self.zone(points)
        with self.assertRaises(ValidationError):
            CountingConfig(
                reference_width=100, reference_height=100, zones=[zone, zone]
            )

    def test_bottom_center_boundary_overlap_and_no_accumulation(self) -> None:
        """Điểm neo là giữa đáy bbox; hai vùng độc lập và frame mới không cộng dồn."""
        zone = self.zone([(0, 0), (0.5, 0), (0.5, 1), (0, 1)])
        second = self.zone([(0, 0), (1, 0), (1, 1), (0, 1)], classes=["wheelchair"])
        config = CountingConfig(
            reference_width=200, reference_height=100, zones=[zone, second]
        )
        frame = {
            "frameId": 2,
            "timestampMs": 200,
            "sourceSize": {"width": 200, "height": 100},
            "detections": [
                {"label": "person", "bbox": [80, 0, 120, 80]},
                {"label": "wheelchair", "bbox": [20, 0, 60, 90]},
                {"label": "person", "bbox": [120, 0, 180, 80]},
                {"label": "cat", "bbox": [0, 0, 10, 10]},
                {"label": "IV pole", "bbox": [float("nan"), 0, 10, 10]},
            ],
        }
        result = count_frame(frame, config)
        self.assertTrue(result["valid"])
        self.assertEqual(result["regions"][0]["counts"]["person"], 1)
        self.assertEqual(result["regions"][0]["counts"]["wheelchair"], 1)
        self.assertEqual(result["regions"][1]["counts"], {"wheelchair": 1})
        self.assertEqual(len(result["regions"][0]["counts"]), len(CLASSES))
        empty = count_frame({**frame, "detections": []}, config)
        self.assertTrue(all(v == 0 for v in empty["regions"][0]["counts"].values()))
        self.assertEqual(count_frame(frame, config), result)
        self.assertEqual(frame["detections"][0]["label"], "person")

    def test_frame_size_scaling_and_aspect_mismatch(self) -> None:
        """Thay độ phân giải cùng tỷ lệ vẫn đếm đúng; đổi tỷ lệ trả invalid thay vì 0."""
        config = CountingConfig(
            reference_width=200,
            reference_height=100,
            zones=[self.zone([(0, 0), (1, 0), (1, 1), (0, 1)])],
        )
        result = {
            "sourceSize": {"width": 400, "height": 200},
            "detections": [{"label": "IV pole", "bbox": [10, 20, 30, 50]}],
        }
        self.assertEqual(
            count_frame(result, config)["regions"][0]["counts"]["IV pole"], 1
        )
        invalid = count_frame(
            {**result, "sourceSize": {"width": 100, "height": 100}}, config
        )
        self.assertFalse(invalid["valid"])
        self.assertEqual(invalid["regions"], [])

    def test_custom_classes_and_legacy_defaults(self) -> None:
        """Đếm nhãn tuỳ chỉnh, giữ bộ mặc định cũ và không tính nhãn ngoài prompt."""
        zone = self.zone(
            [(0, 0), (1, 0), (1, 1), (0, 1)], classes=["laptop", "cell phone"]
        )
        config = CountingConfig(
            reference_width=100,
            reference_height=100,
            classes=["laptop", "cell phone", "car"],
            zones=[zone],
        )
        result = count_frame(
            {
                "sourceSize": {"width": 100, "height": 100},
                "detections": [
                    {"label": "laptop", "bbox": [0, 0, 20, 20]},
                    {"label": "cell phone", "bbox": [10, 10, 30, 30]},
                    {"label": "person", "bbox": [0, 0, 10, 10]},
                    {"label": "car", "bbox": [0, 0, 10, 10]},
                ],
            },
            config,
        )
        self.assertEqual(result["regions"][0]["counts"], {"laptop": 1, "cell phone": 1})
        self.assertEqual(
            CountingConfig(reference_width=100, reference_height=100).classes,
            list(CLASSES),
        )

    def test_invalid_custom_classes_and_zone_membership(self) -> None:
        """Chặn class rỗng/trùng/quá dài/điều khiển và vùng chọn class ngoài prompt."""
        for classes in [
            [],
            ["person", "PERSON"],
            [" "],
            ["x" * 81],
            ["a\tb"],
            [str(i) for i in range(81)],
        ]:
            with self.subTest(classes=classes), self.assertRaises(ValidationError):
                CountingConfig(
                    reference_width=100, reference_height=100, classes=classes
                )
        with self.assertRaises(ValidationError):
            CountingConfig(
                reference_width=100,
                reference_height=100,
                classes=["laptop"],
                zones=[self.zone([(0, 0), (1, 0), (1, 1)], classes=["person"])],
            )
        config = CountingConfig(
            reference_width=100, reference_height=100, classes=[" laptop "]
        )
        self.assertEqual(config.classes, ["laptop"])


# ------------------------- Kiểm thử nâng cấp cấu hình ------------------------
class ProfileMigrationTests(unittest.TestCase):
    """Bảo toàn cấu hình nguồn cũ khi chuyển sang danh sách có tên trong SQLite."""

    def test_legacy_settings_are_imported_once_with_run_pointer(self) -> None:
        """Migration giữ snapshot, chữ ký và ID lượt; chạy startup lại không nhân đôi."""
        import json
        import tempfile
        from pathlib import Path

        from app.db.migrations import initialize_database

        with tempfile.TemporaryDirectory() as temporary:
            database = initialize_database(Path(temporary) / "test.sqlite3")
            saved = {
                "source_signature": "a" * 64,
                "config": {"classes": ["person"], "zones": []},
                "monitor": {"model_id": "yoloe.pt", "options": {"conf": 0.25}},
            }
            source_id = str(uuid4())
            with database.connection() as connection:
                connection.execute("DROP TABLE counting_profiles")
                connection.execute("PRAGMA user_version=5")
                connection.execute(
                    "INSERT INTO sources VALUES (?,?,?,?,?,?,?)",
                    (
                        source_id,
                        "Video",
                        "video",
                        "/tmp/video.mp4",
                        json.dumps(
                            {
                                "zone_counting": saved,
                                "zone_counting_run": {"id": "legacy-run"},
                            }
                        ),
                        "2026-01-01",
                        "2026-01-01",
                    ),
                )
            initialize_database(database.path)
            initialize_database(database.path)
            with database.connection() as connection:
                rows = connection.execute("SELECT * FROM counting_profiles").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "Cấu hình 1")
            self.assertEqual(rows[0]["source_id"], source_id)
            self.assertEqual(rows[0]["current_run_id"], "legacy-run")
            self.assertEqual(json.loads(rows[0]["snapshot_json"]), saved)
