"""Lưu lượt chạy ảnh và kết quả JSON bằng SQLite."""

from app.db.connection import Database
from app.modules.models.repository import timestamp

from .schemas import RunRecord


# ----------------------------- Repository lượt chạy --------------------------
class RunRepository:
    """Truy cập bản ghi chạy; file do service quản lý, mỗi thao tác dùng kết nối ngắn."""

    def __init__(self, database: Database) -> None:
        """Giữ database đã migration, không tạo kết nối lâu dài."""
        self.database = database

    def get(self, run_id: str) -> RunRecord | None:
        """Đọc JSON lượt chạy theo ID; trả None nếu không có."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT record_json FROM runs WHERE id=?", (run_id,)
            ).fetchone()
        return RunRecord.model_validate_json(row["record_json"]) if row else None

    def save(self, record: RunRecord) -> RunRecord:
        """Thêm/cập nhật toàn bộ bản ghi atomically; trả record sau khi ghi thành công."""
        record = record.model_copy(update={"updated_at": timestamp()})
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO runs(id,record_json) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET record_json=excluded.record_json",
                (record.id, record.model_dump_json()),
            )
        return record

    def interrupt(self) -> None:
        """Đánh dấu lượt chạy gián đoạn khi backend khởi động; không xoá ảnh/kết quả cũ."""
        with self.database.connection() as connection:
            rows = connection.execute("SELECT record_json FROM runs").fetchall()
        for row in rows:
            record = RunRecord.model_validate_json(row["record_json"])
            if record.status in {"queued", "running"}:
                self.save(
                    record.model_copy(
                        update={
                            "status": "failed",
                            "error": "Backend đã dừng trong lúc chạy. Hãy chạy lại.",
                        }
                    )
                )

    def expired(self) -> list[RunRecord]:
        """Liệt kê lượt terminal đã hết thời hạn để dọn file và bản ghi cùng nhau."""
        with self.database.connection() as connection:
            rows = connection.execute("SELECT record_json FROM runs").fetchall()
        records = [RunRecord.model_validate_json(row["record_json"]) for row in rows]
        return [
            record
            for record in records
            if record.expires_at <= timestamp()
            and record.status not in {"queued", "running"}
        ]

    def delete(self, run_id: str) -> None:
        """Xoá JSON theo ID sau khi storage đã dọn snapshot, không xoá thư viện source/model."""
        with self.database.connection() as connection:
            connection.execute("DELETE FROM runs WHERE id=?", (run_id,))
