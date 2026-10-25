import tempfile
import unittest
from pathlib import Path

from app.db import initialize_database
from app.db.connection import Database
from app.db.migrations import MIGRATIONS
from app.modules.sources.models import SourceKind
from app.modules.sources.repository import SourceRepository


# ------------------------ Kiểm thử repository source -------------------------
class SourceRepositoryTests(unittest.TestCase):
    """Kiểm tra CRUD và giao dịch repository bằng SQLite tạm; không dùng dữ liệu thật."""

    def setUp(self) -> None:
        """Tạo SQLite và thư mục tạm riêng cho mỗi test; đăng ký dọn dữ liệu sau test."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "nested" / "visionkit.sqlite3"
        self.database = initialize_database(self.path)
        self.sources = SourceRepository(self.database)

    def test_rtsp_survives_reopening_database(self) -> None:
        """Xác minh URL RTSP và metadata tồn tại nguyên vẹn khi mở lại SQLite."""
        location = "rtsp://viewer:secret@192.168.1.10:554/stream?channel=1&subtype=0"
        record = self.sources.create(
            name="Camera cổng chính",
            kind="stream",
            location=location,
            metadata={"width": 1920, "height": 1080, "fps": 25, "tags": ["Cổng chính"]},
        )
        reopened = SourceRepository(initialize_database(self.path)).get(record.id)
        self.assertEqual(reopened, record)
        self.assertEqual(reopened.location, location)
        self.assertEqual(reopened.kind, SourceKind.STREAM)
        self.assertIsNotNone(reopened.created_at.tzinfo)

    def test_file_metadata_update_and_delete(self) -> None:
        """Kiểm tra sửa tên/metadata, giữ thời điểm tạo và hành vi xoá source."""
        record = self.sources.create(
            name="Video", kind="video", location="sources/clip.mp4"
        )
        updated = self.sources.update(
            record.id, name="Video mới", metadata={"duration": 92.5}
        )
        self.assertEqual(updated.metadata, {"duration": 92.5})
        self.assertEqual(updated.created_at, record.created_at)
        self.assertEqual(updated.location, record.location)
        self.assertGreaterEqual(updated.updated_at, record.updated_at)
        self.assertEqual(self.sources.update(record.id, metadata={}).metadata, {})
        self.assertTrue(self.sources.delete(record.id))
        self.assertIsNone(self.sources.get(record.id))
        self.assertFalse(self.sources.delete(record.id))
        self.assertIsNone(self.sources.update(record.id, name="Missing"))

    def test_filter_and_pagination(self) -> None:
        """Kiểm tra lọc theo loại, thứ tự mới nhất trước và phân trang."""
        first = self.sources.create(
            name="Ảnh", kind="image", location="sources/image.jpg"
        )
        second = self.sources.create(
            name="Camera", kind="stream", location="rtsp://camera.local/live"
        )
        self.assertEqual(self.sources.list(kind="image"), [first])
        self.assertEqual(self.sources.list(limit=1), [second])
        self.assertEqual(self.sources.list(limit=1, offset=1), [first])
        self.assertEqual(self.sources.list(offset=10), [])

    def test_invalid_input_cannot_change_existing_data(self) -> None:
        """Dữ liệu không hợp lệ phải bị từ chối và không làm thay đổi bản ghi hiện có."""
        record = self.sources.create(
            name="Original", kind="image", location="source.jpg"
        )
        invalid = [
            {"name": " ", "kind": "image", "location": "image.jpg"},
            {"name": "Bad", "kind": "stream", "location": "not-a-url"},
            {"name": "Bad", "kind": "stream", "location": "file:///tmp/file"},
            {"name": "Bad", "kind": "unknown", "location": "file"},
            {"name": "Bad", "kind": "image", "location": " "},
            {
                "name": "Bad",
                "kind": "image",
                "location": "file",
                "metadata": {"fps": float("nan")},
            },
        ]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.sources.create(**values)
        with self.assertRaises(ValueError):
            self.sources.update(record.id, name=" ")
        self.assertEqual(self.sources.get(record.id), record)
        self.assertEqual(self.sources.list(), [record])
        for arguments in ({"limit": 0}, {"limit": 1001}, {"offset": -1}):
            with self.assertRaises(ValueError):
                self.sources.list(**arguments)

    def test_values_are_bound_as_parameters(self) -> None:
        """Chuỗi chứa SQL được lưu như dữ liệu, không thực thi thành câu lệnh."""
        name = "Camera'); DROP TABLE sources; --"
        record = self.sources.create(
            name=name, kind="image", location="sources/ảnh '01'.jpg"
        )
        self.assertEqual(self.sources.get(record.id).name, name)
        self.assertEqual(len(self.sources.list()), 1)
        self.assertIsNone(self.sources.get("' OR 1=1 --"))

    def test_migration_is_idempotent_and_uses_wal(self) -> None:
        """Khởi tạo lại giữ dữ liệu, phiên bản schema, WAL và foreign_keys."""
        self.sources.create(
            name="Camera", kind="stream", location="rtsp://camera.local/live"
        )
        initialize_database(self.path)
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("PRAGMA user_version").fetchone()[0], len(MIGRATIONS)
            )
            self.assertEqual(
                connection.execute("PRAGMA journal_mode").fetchone()[0], "wal"
            )
            self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(len(self.sources.list()), 1)

    def test_connection_rolls_back_on_error(self) -> None:
        """Lỗi trong giao dịch phải rollback phần dữ liệu đã ghi."""
        with self.assertRaises(RuntimeError):
            with self.database.connection() as connection:
                connection.execute("CREATE TABLE should_rollback (id INTEGER)")
                connection.execute("INSERT INTO should_rollback VALUES (1)")
                raise RuntimeError("Simulated failure")
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM should_rollback").fetchone()[
                    0
                ],
                0,
            )

    def test_newer_schema_is_rejected(self) -> None:
        """Không cho backend cũ mở schema có phiên bản mới hơn hỗ trợ."""
        with self.database.connection() as connection:
            connection.execute("PRAGMA user_version = 999")
        with self.assertRaises(RuntimeError):
            initialize_database(self.path)

    def test_upgrade_sources_database_to_models_schema(self) -> None:
        """Nâng DB phiên bản 1 lên schema mới, giữ nguyên source và thêm bảng model rỗng."""
        old_path = self.path.parent / "previous.sqlite3"
        previous = Database(old_path)
        with previous.connection() as connection:
            for statement in MIGRATIONS[0]:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 1")
        source = SourceRepository(previous).create(
            name="Ảnh cũ", kind="image", location="original.png"
        )
        upgraded = initialize_database(old_path)
        self.assertEqual(SourceRepository(upgraded).get(source.id), source)
        with upgraded.connection() as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM models").fetchone()[0], 0
            )
            self.assertEqual(
                connection.execute("SELECT count(*) FROM model_downloads").fetchone()[
                    0
                ],
                0,
            )


if __name__ == "__main__":
    unittest.main()
