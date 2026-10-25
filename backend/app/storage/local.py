"""Lưu ảnh gốc và preview bằng tên do backend tạo, tách khỏi SQLite."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import SourceError
from app.storage.image_processing import inspect_image
from app.storage.video_processing import inspect_video


# ---------------------------- Lưu trữ file local -----------------------------
class LocalStorage:
    """Quản lý file ảnh và JPEG preview trong một thư mục gốc.

    Thuộc tính:
        root: Thư mục tuyệt đối chứa file do backend quản lý.
        settings: Giới hạn dung lượng upload và số pixel ảnh.
    """

    def __init__(self, settings: Settings) -> None:
        """Nhận cấu hình và tạo thư mục nguồn; OSError báo lỗi quyền truy cập."""
        self.root = settings.sources_path.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = settings

    def path(self, location: str) -> Path:
        """Trả đường dẫn nằm trong storage; SourceError 404 nếu đi ra ngoài gốc."""
        path = (self.root / location).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise SourceError(404, "Không tìm thấy nội dung source.")
        return path

    @contextmanager
    def temporary_upload(
        self, stream: BinaryIO, limit: int | None = None
    ) -> Iterator[tuple[Path, int]]:
        """Ghi upload theo khối vào file tạm và luôn dọn sau khi thoát context.

        Tham số:
            stream: File nhị phân được đọc lại từ đầu, không tự đóng tại đây.
            limit: Giới hạn byte riêng; mặc định dùng giới hạn ảnh.
        Trả về:
            Context manager cung cấp đường dẫn tạm và dung lượng đã ghi.
        Ngoại lệ:
            SourceError: 413 khi quá giới hạn dung lượng.
            OSError: Không ghi/đọc/xoá được file tạm.
        """
        limit = self.settings.max_upload_bytes if limit is None else limit
        temporary = self.root / f"{uuid4().hex}.part"
        try:
            size = 0
            stream.seek(0)
            with temporary.open("xb") as output:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise SourceError(
                            413,
                            f"Tệp vượt giới hạn upload {limit // (1024 * 1024)} MB.",
                        )
                    output.write(chunk)
            yield temporary, size
        finally:
            temporary.unlink(missing_ok=True)

    def inspect(self, stream: BinaryIO) -> tuple[dict[str, Any], bytes]:
        """Tạo metadata/JPEG tạm để xem HEIC trước khi lưu vào thư viện.

        Không tạo bản ghi SQLite hoặc giữ file lâu dài. Trả metadata và JPEG
        bytes; lỗi ảnh/giới hạn dung lượng được chuyển thành SourceError.
        """
        with self.temporary_upload(stream) as (temporary, size):
            metadata, preview = inspect_image(
                temporary, self.settings.max_image_pixels, make_preview=True
            )
            metadata["size"] = size
            if preview is None:
                raise SourceError(415, "Không tạo được preview cho ảnh.")
            return metadata, preview

    def save_image(self, stream: BinaryIO, filename: str) -> tuple[str, dict[str, Any]]:
        """Xác minh và lưu file gốc; tạo JPEG sidecar khi ảnh là HEIC/HEIF.

        Tham số:
            stream: Nội dung nhị phân của file upload.
            filename: Tên gốc chỉ dùng cho metadata, không dùng làm tên file lưu.
        Trả về:
            Vị trí file gốc và metadata; preview_location xuất hiện với HEIC.
        Ngoại lệ:
            SourceError: Ảnh hỏng hoặc vượt giới hạn.
            OSError: Không ghi được file; mọi file vừa tạo được dọn nếu lỗi.
        """
        created: list[Path] = []
        try:
            with self.temporary_upload(stream) as (temporary, size):
                metadata, preview = inspect_image(
                    temporary, self.settings.max_image_pixels
                )
                location = f"{uuid4().hex}.{metadata.pop('extension')}"
                if preview is not None:
                    preview_location = f"{Path(location).stem}.preview.jpg"
                    preview_path = self.path(preview_location)
                    created.append(preview_path)
                    preview_path.write_bytes(preview)
                    metadata.update(
                        preview_location=preview_location,
                        preview_mime_type="image/jpeg",
                    )
                original_path = self.path(location)
                temporary.replace(original_path)
                created.append(original_path)
                metadata.update(
                    size=size, original_filename=Path(filename.replace("\\", "/")).name
                )
                return location, metadata
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise

    def save_video(self, stream: BinaryIO, filename: str) -> tuple[str, dict[str, Any]]:
        """Lưu video gốc và thumbnail sau khi xác minh bằng FFmpeg.

        Tham số:
            stream: File nhị phân đọc lại từ đầu.
            filename: Tên gốc chỉ dùng cho metadata.
        Trả về:
            Tên file gốc tương đối và metadata kèm vị trí thumbnail.
        Ngoại lệ:
            SourceError: Quá dung lượng, video lỗi hoặc thiếu FFmpeg.
            OSError: Không ghi được file; dọn mọi file vừa tạo khi thất bại.
        """
        created: list[Path] = []
        try:
            with self.temporary_upload(
                stream, self.settings.max_video_upload_bytes
            ) as (temporary, size):
                metadata, preview = inspect_video(temporary)
                location = f"{uuid4().hex}.{metadata.pop('extension')}"
                preview_location = f"{Path(location).stem}.preview.jpg"
                preview_path = self.path(preview_location)
                created.append(preview_path)
                preview_path.write_bytes(preview)
                original_path = self.path(location)
                temporary.replace(original_path)
                created.append(original_path)
                metadata.update(
                    size=size,
                    original_filename=Path(filename.replace("\\", "/")).name,
                    preview_location=preview_location,
                    preview_mime_type="image/jpeg",
                )
                return location, metadata
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise

    def source_paths(self, location: str, metadata: dict[str, Any]) -> list[Path]:
        """Trả các file gốc/preview thuộc source, dùng để xoá hoặc rollback cùng nhau.

        Tham số:
            location: Tên file gốc tương đối trong storage.
            metadata: Có thể chứa preview_location của JPEG sidecar.
        Ngoại lệ:
            SourceError: Một trong các đường dẫn đi ra ngoài thư mục quản lý.
        """
        paths = [self.path(location)]
        if metadata.get("preview_location"):
            preview = self.path(metadata["preview_location"])
            if preview not in paths:
                paths.append(preview)
        return paths
