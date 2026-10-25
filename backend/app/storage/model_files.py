"""Tải weights theo luồng và kiểm tra checksum, không giải mã hoặc load model."""

import hashlib
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import httpx

from app.core.errors import SourceError
from app.modules.models.schemas import DownloadJob


# ------------------------------ Lưu file model -------------------------------
class ModelFiles:
    """Quản lý file model trong root; tên file nội bộ lấy từ UUID của lượt tải."""

    def __init__(self, root: Path, max_bytes: int) -> None:
        """Tạo root và giữ giới hạn max_bytes; OSError báo lỗi quyền truy cập đĩa."""
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def path(self, location: str) -> Path:
        """Trả đường dẫn trong root; SourceError 404 nếu location trỏ ra ngoài storage."""
        path = (self.root / location).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise SourceError(404, "Không tìm thấy file model.")
        return path

    def recover(self) -> None:
        """Dọn file .part của lượt bị ngắt khi khởi động worker đơn; không xoá weights."""
        for path in self.root.glob("*.part"):
            path.unlink(missing_ok=True)

    def save_upload(
        self, stream: BinaryIO, filename: str, limit: int
    ) -> tuple[str, int, str]:
        """Lưu model upload theo khối, tính SHA-256 và không giải mã weights.

        Tham số:
            stream: File nhị phân được đọc lại từ đầu; nơi gọi tự đóng file.
            filename: Tên gốc, chỉ lấy đuôi pt/onnx để đặt tên file nội bộ.
            limit: Giới hạn byte dành riêng cho upload.
        Trả về:
            Vị trí file tương đối, số byte thực và SHA-256.
        Ngoại lệ:
            SourceError: 415 nếu sai đuôi, 422 nếu file rỗng, 413 nếu quá giới hạn.
            OSError: Không ghi được file. File tạm luôn được dọn khi lỗi.
        """
        extension = Path(filename).suffix.lower()
        if extension not in (".pt", ".onnx"):
            raise SourceError(415, "Chỉ hỗ trợ model .pt hoặc .onnx.")
        temporary = self.path(f"{uuid4()}.part")
        location = f"{uuid4()}{extension}"
        size = 0
        digest = hashlib.sha256()
        try:
            stream.seek(0)
            with temporary.open("xb") as output:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise SourceError(
                            413,
                            f"Model vượt giới hạn upload {limit // (1024 * 1024)} MB.",
                        )
                    digest.update(chunk)
                    output.write(chunk)
            if size == 0:
                raise SourceError(422, "Tệp model đang rỗng. Chọn lại tệp.")
            temporary.replace(self.path(location))
            return location, size, digest.hexdigest()
        finally:
            temporary.unlink(missing_ok=True)

    async def download(
        self,
        job: DownloadJob,
        client: httpx.AsyncClient,
        report: Callable[[int], Awaitable[None]],
    ) -> tuple[str, str]:
        """Tải file đã duyệt vào .part, xác minh byte/SHA-256 rồi đổi tên thành .pt.

        Tham số:
            job: Lượt tải chứa URL chính thức, dung lượng và checksum đã ghim.
            client: HTTP client có timeout và hỗ trợ redirect của GitHub.
            report: Callback nhận byte thật theo nhịp tối đa bốn lần mỗi giây.
        Trả về:
            Tên file tương đối và SHA-256 đã xác minh.
        Ngoại lệ:
            SourceError: 413 khi quá dung lượng; 502 khi file tải không khớp.
            httpx.HTTPError/OSError: Lỗi mạng hoặc ghi đĩa.
        Tác động phụ:
            Tạo file gốc khi thành công, luôn dọn file tạm khi lỗi hoặc huỷ.
        """
        temporary = self.path(f"{job.id}.part")
        received = 0
        digest = hashlib.sha256()
        last_report = 0.0
        try:
            async with client.stream("GET", job.variant.url) as response:
                response.raise_for_status()
                header_size = response.headers.get("Content-Length")
                if header_size is not None and int(header_size) != job.total_bytes:
                    raise SourceError(
                        502,
                        "Dung lượng model trên nguồn đã thay đổi. Hãy cập nhật danh mục.",
                    )
                with temporary.open("xb") as output:
                    async for chunk in response.aiter_bytes(256 * 1024):
                        received += len(chunk)
                        if received > min(self.max_bytes, job.total_bytes):
                            raise SourceError(
                                413, "Model vượt giới hạn dung lượng cho phép."
                            )
                        output.write(chunk)
                        digest.update(chunk)
                        if time.monotonic() - last_report >= 0.25:
                            await report(received)
                            last_report = time.monotonic()
            checksum = digest.hexdigest()
            if received != job.total_bytes or checksum != job.variant.sha256:
                raise SourceError(
                    502, "Model tải chưa đầy đủ hoặc sai checksum. Hãy thử lại."
                )
            await report(received)
            location = f"{job.id}.pt"
            temporary.replace(self.path(location))
            return location, checksum
        finally:
            temporary.unlink(missing_ok=True)
