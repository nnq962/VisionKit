"""Ghi trạng thái tải và model vào SQLite bằng các kết nối ngắn hạn."""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.connection import Database

from .schemas import (
    CatalogVariant,
    DownloadJob,
    ModelArtifact,
    ModelInspection,
    StoredModel,
)


# ----------------------------- Dấu thời gian UTC -----------------------------
def timestamp() -> str:
    """Trả thời điểm UTC hiện tại dạng ISO để sắp xếp bản ghi và lưu trạng thái."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


# ----------------------------- Repository model ------------------------------
class ModelRepository:
    """Quản lý bản ghi model và download; không tải mạng hoặc mở file weights."""

    def __init__(self, database: Database) -> None:
        """Giữ database đã áp dụng migration; mỗi method tự đóng kết nối của mình."""
        self.database = database

    def models(self) -> list[StoredModel]:
        """Trả tất cả model đã lưu, mới nhất trước; dữ liệu chỉ gồm metadata."""
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM models WHERE expires_at IS NULL ORDER BY saved_at DESC"
            ).fetchall()
        return [
            StoredModel(
                **dict(row),
                variant=json.loads(row["variant_json"]),
                inspection=json.loads(row["inspection_json"]),
            )
            for row in rows
        ]

    def model(self, model_id: str) -> StoredModel | None:
        """Tìm model theo ID catalog hoặc UUID upload; trả None nếu chưa lưu hoặc đã xoá."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM models WHERE id = ?", (model_id,)
            ).fetchone()
        return (
            StoredModel(
                **dict(row),
                variant=json.loads(row["variant_json"]),
                inspection=json.loads(row["inspection_json"]),
            )
            if row
            else None
        )

    def job(self, job_id: str) -> DownloadJob | None:
        """Đọc download theo UUID, trả None khi không tồn tại."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM model_downloads WHERE id = ?", (job_id,)
            ).fetchone()
        return (
            DownloadJob(**dict(row), variant=json.loads(row["variant_json"]))
            if row
            else None
        )

    def jobs(self) -> list[DownloadJob]:
        """Trả mọi lượt đang tải và tối đa 50 lượt kết thúc gần nhất để theo dõi lỗi."""
        with self.database.connection() as connection:
            rows = connection.execute("""SELECT * FROM model_downloads WHERE status IN ('queued','downloading')
                OR id IN (SELECT id FROM model_downloads ORDER BY created_at DESC LIMIT 50)
                ORDER BY created_at DESC""").fetchall()
        return [
            DownloadJob(**dict(row), variant=json.loads(row["variant_json"]))
            for row in rows
        ]

    def create_job(self, variant: CatalogVariant) -> DownloadJob:
        """Tạo lượt tải queued hoặc trả lượt đang chạy cùng model, tránh tải trùng.

        Nhận variant đã kiểm tra; trả job mới/cũ. Transaction khoá ghi bảo đảm
        kiểm tra và thêm là một thao tác; SQLiteError báo lỗi lưu dữ liệu.
        """
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT id FROM model_downloads WHERE catalog_id = ? AND status IN ('queued','downloading')",
                (variant.id,),
            ).fetchone()
            if current:
                job_id = current["id"]
            else:
                job_id, now = str(uuid4()), timestamp()
                connection.execute(
                    """INSERT INTO model_downloads
                    (id,catalog_id,variant_json,status,total_bytes,created_at,updated_at)
                    VALUES (?,?,?,'queued',?,?,?)""",
                    (
                        job_id,
                        variant.id,
                        variant.model_dump_json(),
                        variant.expected_bytes,
                        now,
                        now,
                    ),
                )
        return self.job(job_id)

    def update(
        self, job_id: str, status: str, downloaded: int, error: str | None = None
    ) -> None:
        """Ghi trạng thái/status, byte đã tải và lỗi cho job_id; cập nhật mốc thời gian."""
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE model_downloads SET status=?, downloaded_bytes=?, error=?, updated_at=? WHERE id=?",
                (status, downloaded, error, timestamp(), job_id),
            )

    def complete(self, job: DownloadJob, location: str, digest: str) -> None:
        """Thêm model và đánh dấu download completed trong cùng transaction.

        Nhận job, vị trí file đã đổi tên và checksum đã kiểm tra. Ghi model cùng
        trạng thái tải; lỗi SQLite rollback cả hai bản ghi để service dọn file.
        """
        now = timestamp()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO models (id,variant_json,location,size_bytes,sha256,saved_at) VALUES (?,?,?,?,?,?)",
                (
                    job.variant.id,
                    job.variant.model_dump_json(),
                    location,
                    job.total_bytes,
                    digest,
                    now,
                ),
            )
            connection.execute(
                "UPDATE model_downloads SET status='completed', downloaded_bytes=total_bytes, error=NULL, updated_at=? WHERE id=?",
                (now, job.id),
            )

    def create_uploaded(
        self,
        variant: ModelArtifact,
        location: str,
        size: int,
        digest: str,
        temporary: bool = False,
    ) -> StoredModel:
        """Ghi metadata model upload và trả bản ghi đã lưu.

        Nhận variant khai báo, vị trí file, dung lượng thực và checksum; không
        load weights. temporary=True đặt hạn dùng 24 giờ và ẩn khỏi thư viện;
        False giữ model lâu dài. Lỗi SQLite rollback bản ghi để service dọn file mới.
        """
        now = timestamp()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO models (id,variant_json,location,size_bytes,sha256,saved_at,expires_at) VALUES (?,?,?,?,?,?,?)",
                (
                    variant.id,
                    variant.model_dump_json(),
                    location,
                    size,
                    digest,
                    now,
                    self.expiry() if temporary else None,
                ),
            )
        return self.model(variant.id)

    def expiry(self) -> str:
        """Trả hạn dùng tạm 24 giờ từ hiện tại theo UTC, không ghi DB."""
        return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(
            timespec="microseconds"
        )

    def touch(self, model_id: str) -> None:
        """Gia hạn model tạm còn hiệu lực thêm 24 giờ khi được truy cập; không đổi model thư viện."""
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE models SET expires_at=? WHERE id=? AND expires_at>?",
                (self.expiry(), model_id, timestamp()),
            )

    def expired_ids(self) -> list[str]:
        """Liệt kê ID model tạm hết hạn để service huỷ inspect và dọn file/DB."""
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id FROM models WHERE expires_at<=?", (timestamp(),)
            ).fetchall()
        return [row["id"] for row in rows]

    def promote(self, model_id: str, name: str) -> StoredModel:
        """Chuyển model tạm sang thư viện trong transaction, giữ file/metadata/ID và đặt tên mới.

        Service kiểm tra model tồn tại/còn hạn trước khi gọi. Không sao chép
        hoặc upload lại weights; gọi lại với model đã lưu không tạo bản sao.
        """
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT variant_json FROM models WHERE id=?", (model_id,)
            ).fetchone()
            variant = json.loads(row["variant_json"])
            variant["name"] = name
            connection.execute(
                "UPDATE models SET expires_at=NULL,variant_json=?,saved_at=? WHERE id=?",
                (json.dumps(variant, ensure_ascii=False), timestamp(), model_id),
            )
        return self.model(model_id)

    def set_inspection(
        self, model_id: str, result: ModelInspection
    ) -> StoredModel | None:
        """Lưu kết quả inspect và cập nhật family/task chỉ khi AI thực sự đọc được.

        Nhận model_id và result; trả bản ghi mới hoặc None nếu đã bị xoá. Dùng
        transaction để variant và trạng thái metadata không lệch nhau khi poll.
        """
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT variant_json FROM models WHERE id=?", (model_id,)
            ).fetchone()
            if row is None:
                return None
            variant = json.loads(row["variant_json"])
            metadata = result.metadata
            if result.status in ("ready", "needs_input") and metadata:
                if metadata.family and variant.get("origin") == "upload":
                    variant.update(
                        familyId=metadata.family,
                        familyName="YOLOE" if metadata.family == "yoloe" else "YOLO",
                    )
                if metadata.task:
                    variant["task"] = metadata.task
                if metadata.scale:
                    variant["size"] = metadata.scale
            result = result.model_copy(update={"updated_at": timestamp()})
            connection.execute(
                "UPDATE models SET variant_json=?, inspection_json=? WHERE id=?",
                (
                    json.dumps(variant, ensure_ascii=False),
                    result.model_dump_json(),
                    model_id,
                ),
            )
        return self.model(model_id)

    def configure(self, model_id: str, family: str, task: str) -> StoredModel | None:
        """Ghi family/task khai báo thủ công và đánh dấu manual, giữ metadata AI đọc được."""
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT variant_json,inspection_json FROM models WHERE id=?",
                (model_id,),
            ).fetchone()
            if row is None:
                return None
            variant = json.loads(row["variant_json"])
            variant.update(
                familyId=family,
                familyName="YOLOE" if family == "yoloe" else "YOLO",
                task=task,
            )
            inspection = ModelInspection.model_validate_json(
                row["inspection_json"]
            ).model_copy(
                update={"status": "manual", "message": None, "updated_at": timestamp()}
            )
            connection.execute(
                "UPDATE models SET variant_json=?,inspection_json=? WHERE id=?",
                (
                    json.dumps(variant, ensure_ascii=False),
                    inspection.model_dump_json(),
                    model_id,
                ),
            )
        return self.model(model_id)

    def interrupt_inspections(self) -> None:
        """Đánh dấu các lượt queued/processing là unavailable khi backend dừng hoặc khởi động lại."""
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id,inspection_json FROM models"
            ).fetchall()
            for row in rows:
                current = ModelInspection.model_validate_json(row["inspection_json"])
                if current.status in ("queued", "processing"):
                    current = current.model_copy(
                        update={
                            "status": "unavailable",
                            "message": "Đọc metadata bị gián đoạn. Hãy thử lại.",
                            "updated_at": timestamp(),
                        }
                    )
                    connection.execute(
                        "UPDATE models SET inspection_json=? WHERE id=?",
                        (current.model_dump_json(), row["id"]),
                    )

    def delete(self, model_id: str) -> None:
        """Xoá metadata model_id; service chịu trách nhiệm dọn file và rollback file."""
        with self.database.connection() as connection:
            connection.execute("DELETE FROM models WHERE id=?", (model_id,))

    def interrupt(self) -> None:
        """Đánh dấu lượt đang tải là failed khi khởi động lại worker, không tự tải tiếp."""
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE model_downloads SET status='failed', error=?, updated_at=? WHERE status IN ('queued','downloading')",
                (
                    "Tải bị gián đoạn do backend khởi động lại. Hãy thử lại.",
                    timestamp(),
                ),
            )
