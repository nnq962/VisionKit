"""Quản lý vòng đời kết nối SQLite và đường dẫn dữ liệu local."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


# ----------------------------- Đường dẫn SQLite ------------------------------
def default_database_path() -> Path:
    """Trả đường dẫn SQLite tuyệt đối từ VISIONKIT_DB_PATH hoặc data/ ở gốc repo.

    Hàm chỉ tính đường dẫn, không tạo thư mục hoặc mở kết nối database.
    """
    configured = os.environ.get("VISIONKIT_DB_PATH")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else (Path(__file__).resolve().parents[3] / "data" / "visionkit.sqlite3")
    )


# ------------------------------ Kết nối SQLite -------------------------------
class Database:
    """Quản lý đường dẫn SQLite và cung cấp kết nối ngắn hạn cho mỗi thao tác.

    Thuộc tính:
        path: Đường dẫn tuyệt đối đến file DB. Gọi initialize_database trước
            khi dùng repository; đối tượng không giữ kết nối mở thường trực.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        """Nhận path tuỳ chọn và lưu đường dẫn tuyệt đối; chưa mở hoặc tạo DB."""
        self.path = (
            Path(path).expanduser().resolve()
            if path is not None
            else default_database_path()
        )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Mở kết nối có row_factory và foreign_keys, đóng sau khi dùng xong.

        Trả về:
            Context manager cung cấp sqlite3.Connection.
        Ngoại lệ:
            sqlite3.Error: Không mở được DB hoặc câu lệnh SQL thất bại.
        Tác động phụ:
            Commit giao dịch khi thành công, rollback khi có ngoại lệ và luôn
            đóng kết nối; chờ tối đa 10 giây khi database bị khoá.
        """
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.create_function("casefold", 1, str.casefold, deterministic=True)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()
