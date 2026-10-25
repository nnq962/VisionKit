"""Lưu thông tin source vào SQLite; file media được quản lý riêng trên đĩa."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from app.db.connection import Database

from .models import Source, SourceKind


# -------------------------- Kiểm tra chuỗi bắt buộc --------------------------
def _required(value: str, field: str) -> str:
    """Kiểm tra chuỗi bắt buộc và trả giá trị đã bỏ khoảng trắng hai đầu.

    Tham số:
        value: Giá trị cần kiểm tra.
        field: Tên trường dùng trong thông báo lỗi.
    Ngoại lệ:
        ValueError: Giá trị không phải chuỗi hoặc chuỗi rỗng.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value.strip()


# -------------------------- Chuẩn hoá vị trí source --------------------------
def _location(value: str, kind: SourceKind) -> str:
    """Chuẩn hoá vị trí source và kiểm tra giao thức với nguồn URL.

    Tham số:
        value: Đường dẫn file, URL hoặc định danh thiết bị.
        kind: Loại source để chọn giao thức URL được chấp nhận.
    Trả về:
        Vị trí đã bỏ khoảng trắng hai đầu; không kiểm tra kết nối mạng.
    Ngoại lệ:
        ValueError: Vị trí rỗng hoặc URL không có host/giao thức phù hợp.
    """
    value = _required(value, "location")
    if kind in (SourceKind.STREAM, SourceKind.URL, SourceKind.YOUTUBE):
        parsed = urlsplit(value)
        protocols = (
            {"rtsp", "rtsps", "rtmp", "http", "https"}
            if kind == SourceKind.STREAM
            else {"http", "https"}
        )
        if parsed.scheme.lower() not in protocols or not parsed.hostname:
            raise ValueError(f"Invalid URL for source kind {kind.value}.")
    return value


# ------------------------------ Mã hoá metadata ------------------------------
def _metadata(value: dict[str, Any] | None) -> str:
    """Mã hoá dict metadata thành JSON Unicode để lưu vào SQLite.

    None được đổi thành object rỗng. Trả chuỗi JSON; ValueError hoặc TypeError
    báo kiểu dữ liệu không phù hợp, số không hữu hạn hoặc giá trị không mã hoá được.
    """
    if value is not None and not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object.")
    return json.dumps(
        value if value is not None else {}, ensure_ascii=False, allow_nan=False
    )


# --------------------- Chuyển dòng dữ liệu thành source ----------------------
def _source(row: sqlite3.Row) -> Source:
    """Chuyển một sqlite3.Row hợp lệ thành Source có metadata và thời gian UTC.

    Đầu vào phải có đủ các cột của bảng sources. Trả Source; dữ liệu JSON hoặc
    timestamp không hợp lệ phát sinh ValueError thay vì âm thầm sửa dữ liệu.
    """
    return Source(
        id=row["id"],
        name=row["name"],
        kind=SourceKind(row["kind"]),
        location=row["location"],
        metadata=json.loads(row["metadata_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


# ----------------------------- Repository source -----------------------------
class SourceRepository:
    """Cung cấp thao tác lưu, đọc, lọc, sửa và xoá bản ghi source trong SQLite.

    Thuộc tính:
        database: Database đã được khởi tạo schema. Mỗi thao tác tự quản lý
            transaction/kết nối; lớp không tải URL hoặc lưu/xoá file media.
    """

    def __init__(self, database: Database) -> None:
        """Nhận database đã khởi tạo schema và giữ lại để các thao tác CRUD dùng chung."""
        self.database = database

    def create(
        self,
        *,
        name: str,
        kind: SourceKind | str,
        location: str,
        metadata: dict[str, Any] | None = None,
    ) -> Source:
        """Tạo và lưu source mới, trả bản ghi với UUID và timestamp UTC.

        Tham số:
            name: Tên hiển thị không rỗng.
            kind: Loại source hợp lệ theo SourceKind.
            location: Đường dẫn, URL hoặc định danh thiết bị.
            metadata: Dict có thể mã hoá JSON; bỏ trống để lưu object rỗng.
        Ngoại lệ:
            ValueError/TypeError: Dữ liệu không hợp lệ hoặc không mã hoá được.
            sqlite3.Error: Không thể ghi DB; giao dịch được rollback.
        Tác động phụ:
            Thêm bản ghi, không tạo file media hoặc kết nối camera.
        """
        kind = SourceKind(kind)
        name = _required(name, "name")
        location = _location(location, kind)
        encoded = _metadata(metadata)
        source_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self.database.connection() as connection:
            connection.execute(
                """INSERT INTO sources
                (id, name, kind, location, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (source_id, name, kind.value, location, encoded, timestamp, timestamp),
            )
            row = connection.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        return _source(row)

    def get(self, source_id: str) -> Source | None:
        """Đọc source theo source_id và trả bản ghi, hoặc None nếu không tồn tại.

        Chỉ truy vấn metadata; không kiểm tra file hoặc kết nối URL.
        """
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        return _source(row) if row else None

    def list(
        self,
        *,
        kind: SourceKind | str | None = None,
        limit: int = 100,
        offset: int = 0,
        q: str = "",
    ) -> list[Source]:
        """Trả source mới nhất trước, có bộ lọc loại và giới hạn phân trang.

        Tham số:
            kind: Lọc SourceKind; None để lấy mọi loại.
            limit: Số bản ghi tối đa, từ 1 đến 1000.
            offset: Số bản ghi bỏ qua, từ 0 trở lên.
            q: Chuỗi tìm trong tên, không phân biệt chữ hoa/thường Unicode.
        Ngoại lệ:
            ValueError: Loại hoặc thông số phân trang không hợp lệ.
        """
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000.")
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be non-negative.")
        where, values = self._filter(kind, q)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM sources{where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (*values, limit, offset),
            ).fetchall()
        return [_source(row) for row in rows]

    def _filter(self, kind: SourceKind | str | None, q: str) -> tuple[str, list[str]]:
        """Tạo điều kiện lọc có bind parameter cho loại và tên Unicode.

        Nhận kind tuỳ chọn và q cần tìm; trả mệnh đề SQL cùng giá trị bind.
        ValueError báo loại không hợp lệ; nội dung người dùng không ghép vào SQL.
        """
        conditions: list[str] = []
        values: list[str] = []
        if kind is not None:
            conditions.append("kind = ?")
            values.append(SourceKind(kind).value)
        if q.strip():
            conditions.append("instr(casefold(name), ?) > 0")
            values.append(q.strip().casefold())
        return (" WHERE " + " AND ".join(conditions) if conditions else ""), values

    def count(self, *, kind: SourceKind | str | None = None, q: str = "") -> int:
        """Đếm bản ghi khớp loại kind và chuỗi tên q để phân trang nhất quán."""
        where, values = self._filter(kind, q)
        with self.database.connection() as connection:
            return connection.execute(
                f"SELECT count(*) FROM sources{where}", values
            ).fetchone()[0]

    def update(
        self,
        source_id: str,
        *,
        name: str | None = None,
        location: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Source | None:
        """Cập nhật source theo ID và trả bản ghi mới, hoặc None nếu không có.

        Tham số:
            source_id: ID cần cập nhật.
            name: Tên mới; None giữ nguyên.
            location: Vị trí mới; None giữ nguyên.
            metadata: Dict thay thế toàn bộ metadata; None giữ nguyên, {} xoá nội dung.
        Ngoại lệ:
            ValueError/TypeError: Dữ liệu không hợp lệ.
            sqlite3.Error: Không ghi được DB; giao dịch được rollback.
        Tác động phụ:
            Cập nhật updated_at trong transaction; không đổi ID, kind hoặc created_at.
        """
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
            if row is None:
                return None
            current = _source(row)
            connection.execute(
                """UPDATE sources SET name = ?, location = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?""",
                (
                    _required(name, "name") if name is not None else current.name,
                    _location(location, current.kind)
                    if location is not None
                    else current.location,
                    _metadata(metadata)
                    if metadata is not None
                    else row["metadata_json"],
                    datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    source_id,
                ),
            )
            updated = connection.execute(
                "SELECT * FROM sources WHERE id = ?", (source_id,)
            ).fetchone()
        return _source(updated)

    def delete(self, source_id: str) -> bool:
        """Xoá bản ghi theo source_id và trả True nếu có bản ghi bị xoá.

        Không xoá file media. Trả False nếu ID không tồn tại; lỗi SQLite được
        chuyển cho service xử lý và giao dịch không thành công sẽ rollback.
        """
        with self.database.connection() as connection:
            return (
                connection.execute(
                    "DELETE FROM sources WHERE id = ?", (source_id,)
                ).rowcount
                > 0
            )
