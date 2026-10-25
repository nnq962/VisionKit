"""Khởi tạo schema theo phiên bản; bổ sung MIGRATIONS khi mở rộng dữ liệu."""

from pathlib import Path

from .connection import Database

MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        """
        CREATE TABLE sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL CHECK (length(trim(name)) > 0),
            kind TEXT NOT NULL CHECK (kind IN (
                'image', 'video', 'stream', 'youtube', 'webcam', 'screen', 'directory', 'url'
            )),
            location TEXT NOT NULL CHECK (length(trim(location)) > 0),
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX sources_kind_created_idx ON sources(kind, created_at DESC, id DESC)",
        "CREATE INDEX sources_created_idx ON sources(created_at DESC, id DESC)",
    ),
    (
        """CREATE TABLE models (
            id TEXT PRIMARY KEY,
            variant_json TEXT NOT NULL,
            location TEXT NOT NULL UNIQUE,
            size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            saved_at TEXT NOT NULL
        )""",
        """CREATE TABLE model_downloads (
            id TEXT PRIMARY KEY,
            catalog_id TEXT NOT NULL,
            variant_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('queued','downloading','completed','failed','cancelled')),
            downloaded_bytes INTEGER NOT NULL DEFAULT 0,
            total_bytes INTEGER NOT NULL,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        "CREATE UNIQUE INDEX model_download_active_idx ON model_downloads(catalog_id) WHERE status IN ('queued','downloading')",
        "CREATE INDEX model_download_created_idx ON model_downloads(created_at DESC)",
    ),
    (
        """ALTER TABLE models ADD COLUMN inspection_json TEXT NOT NULL DEFAULT '{"status":"uninspected"}'""",
    ),
)


# ------------------------ Khởi tạo và nâng cấp schema ------------------------
def initialize_database(path: str | Path | None = None) -> Database:
    """Tạo thư mục chứa SQLite và áp dụng tuần tự các migration chưa chạy.

    Tham số:
        path: Đường dẫn DB tuỳ chọn; bỏ trống để dùng cấu hình môi trường.
    Trả về:
        Database đã bật WAL và có schema tương thích.
    Ngoại lệ:
        RuntimeError: DB có phiên bản schema mới hơn code hiện tại.
        sqlite3.Error hoặc OSError: Không mở/ghi được database hoặc thư mục.
    Tác động phụ:
        Tạo file DB nếu chưa có; migration chạy trong transaction, giữ dữ liệu cũ.
    """
    database = Database(path)
    database.path.parent.mkdir(parents=True, exist_ok=True)
    with database.connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("BEGIN IMMEDIATE")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > len(MIGRATIONS):
            raise RuntimeError("Database schema is newer than this backend supports.")
        for index in range(version, len(MIGRATIONS)):
            for statement in MIGRATIONS[index]:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {index + 1}")
    return database
