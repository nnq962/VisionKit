"""Lưu ảnh, video chuẩn hoá và preview bằng tên do backend tạo, tách khỏi SQLite."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO
from uuid import uuid4

from app.core.config import Settings
from app.core.errors import SourceError
from app.storage.image_processing import inspect_image
from app.storage.video_processing import create_video_playback, inspect_video


# ---------------------------- Lưu trữ file local -----------------------------
class LocalStorage:
    """Quản lý file ảnh và JPEG preview trong một thư mục gốc.

    Thuộc tính:
        root: Thư mục tuyệt đối chứa file do backend quản lý.
        settings: Giới hạn dung lượng upload và số pixel ảnh.
        playback_lock: Tránh chuyển mã trùng khi trình duyệt gửi nhiều range request.
    """

    def __init__(self, settings: Settings) -> None:
        """Nhận cấu hình và tạo thư mục nguồn; OSError báo lỗi quyền truy cập."""
        self.root = settings.sources_path.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self.playback_lock = Lock()

    def path(self, location: str) -> Path:
        """Trả đường dẫn nằm trong storage; SourceError 404 nếu đi ra ngoài gốc."""
        path = (self.root / location).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise SourceError(404, "Không tìm thấy nội dung source.")
        return path

    @contextmanager
    def temporary_upload(
        self, stream: BinaryIO, limit: int | None = None
    ) -> Iterator[tuple[Path, int, str]]:
        """Ghi upload theo khối vào file tạm và luôn dọn sau khi thoát context.

        Tham số:
            stream: File nhị phân được đọc lại từ đầu, không tự đóng tại đây.
            limit: Giới hạn byte riêng; mặc định dùng giới hạn ảnh.
        Trả về:
            Context manager cung cấp đường dẫn tạm, dung lượng và SHA-256 của byte gốc.
        Ngoại lệ:
            SourceError: 413 khi quá giới hạn dung lượng.
            OSError: Không ghi/đọc/xoá được file tạm.
        """
        limit = self.settings.max_upload_bytes if limit is None else limit
        temporary = self.root / f"{uuid4().hex}.part"
        try:
            size = 0
            digest = hashlib.sha256()
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
                    digest.update(chunk)
            yield temporary, size, digest.hexdigest()
        finally:
            temporary.unlink(missing_ok=True)

    def inspect(self, stream: BinaryIO) -> tuple[dict[str, Any], bytes]:
        """Tạo metadata/JPEG tạm để xem HEIC trước khi lưu vào thư viện.

        Không tạo bản ghi SQLite hoặc giữ file lâu dài. Trả metadata và JPEG
        bytes; lỗi ảnh/giới hạn dung lượng được chuyển thành SourceError.
        """
        with self.temporary_upload(stream) as (temporary, size, digest):
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
            with self.temporary_upload(stream) as (temporary, size, digest):
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
                        preview_size=len(preview),
                        preview_location=preview_location,
                        preview_mime_type="image/jpeg",
                    )
                original_path = self.path(location)
                temporary.replace(original_path)
                created.append(original_path)
                metadata.update(
                    size=size,
                    sha256=digest,
                    original_filename=Path(filename.replace("\\", "/")).name,
                )
                return location, metadata
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise

    def save_video(self, stream: BinaryIO, filename: str) -> tuple[str, dict[str, Any]]:
        """Xác minh video, chuyển MOV thành MP4 một lần rồi lưu cùng thumbnail.

        Tham số:
            stream: File nhị phân đọc lại từ đầu.
            filename: Tên gốc chỉ dùng cho metadata.
        Trả về:
            Tên file lưu tương đối và metadata của chính file đó kèm thumbnail.
        Ngoại lệ:
            SourceError: Quá dung lượng, video lỗi hoặc thiếu FFmpeg.
            OSError: Không ghi được file; dọn mọi file vừa tạo khi thất bại.
        Tác động phụ:
            MOV được thay bằng MP4 H.264/AAC; chỉ giữ MP4 và thumbnail, cập nhật
            metadata/hash theo byte đã lưu. Video khác được giữ nguyên.
        """
        created: list[Path] = []
        try:
            with self.temporary_upload(
                stream, self.settings.max_video_upload_bytes
            ) as (temporary, size, digest):
                metadata, preview = inspect_video(temporary)
                stored = temporary
                uploaded_filename = Path(filename.replace("\\", "/")).name
                stored_filename = uploaded_filename
                if metadata["extension"] == "mov":
                    stored = self.root / f"{uuid4().hex}.converted.mp4"
                    created.append(stored)
                    create_video_playback(temporary, stored)
                    metadata, preview = inspect_video(stored)
                    size = stored.stat().st_size
                    checksum = hashlib.sha256()
                    with stored.open("rb") as content:
                        while chunk := content.read(1024 * 1024):
                            checksum.update(chunk)
                    digest = checksum.hexdigest()
                    stored_filename = str(Path(uploaded_filename).with_suffix(".mp4"))
                location = f"{uuid4().hex}.{metadata.pop('extension')}"
                preview_location = f"{Path(location).stem}.preview.jpg"
                preview_path = self.path(preview_location)
                created.append(preview_path)
                preview_path.write_bytes(preview)
                original_path = self.path(location)
                stored.replace(original_path)
                created.append(original_path)
                metadata.update(
                    size=size,
                    sha256=digest,
                    original_filename=stored_filename,
                    preview_size=len(preview),
                    preview_location=preview_location,
                    preview_mime_type="image/jpeg",
                )
                if stored_filename != uploaded_filename:
                    metadata["uploaded_filename"] = uploaded_filename
                return location, metadata
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise

    def prepare_video(self, stream: BinaryIO) -> Path:
        """Tạo MP4 tạm cho bản nháp video, không ghi database hoặc giữ file gốc.

        Tham số:
            stream: File upload cần xác minh, áp dụng giới hạn dung lượng video.
        Trả về:
            Đường dẫn MP4; bên gọi phải xoá sau khi gửi response.
        Ngoại lệ:
            SourceError hoặc OSError: Upload, xác minh hoặc chuyển mã thất bại.
        """
        with self.temporary_upload(stream, self.settings.max_video_upload_bytes) as (
            temporary,
            size,
            digest,
        ):
            inspect_video(temporary)
            output = self.root / f"{uuid4().hex}.draft.mp4"
            create_video_playback(temporary, output)
            return output

    def playback(self, location: str, metadata: dict[str, Any]) -> Path:
        """Lấy video gốc tương thích hoặc tạo và tái dùng MP4 sidecar cho MOV.

        Tham số:
            location: File gốc thuộc storage đã được kiểm tra tồn tại.
            metadata: Container và codec đã xác minh lúc upload.
        Trả về:
            Đường dẫn có thể phát trên web, giữ nguyên video gốc và metadata.
        Ngoại lệ:
            SourceError hoặc OSError: Không tạo hoặc truy cập được MP4.
        Tác động phụ:
            Tạo sidecar lần đầu cho MOV hoặc codec chưa tương thích với web.
        """
        original = self.path(location)
        if original.suffix.lower() != ".mov" and metadata.get("codec") in (
            "h264",
            "vp8",
            "vp9",
            "av1",
            "theora",
        ):
            return original
        output = original.with_name(f"{original.stem}.playback.mp4")
        with self.playback_lock:
            if not output.is_file():
                create_video_playback(original, output)
        return output

    def source_paths(self, location: str, metadata: dict[str, Any]) -> list[Path]:
        """Trả các file gốc/preview thuộc source, dùng để xoá hoặc rollback cùng nhau.

        Tham số:
            location: Tên file gốc tương đối trong storage.
            metadata: Có thể chứa preview_location của JPEG sidecar.
        Ngoại lệ:
            SourceError: Một trong các đường dẫn đi ra ngoài thư mục quản lý.
        """
        paths = [self.path(location)]
        # Sidecar phát video được tạo theo nhu cầu, kể cả với source đã lưu từ trước.
        paths.append(self.path(f"{Path(location).stem}.playback.mp4"))
        if metadata.get("preview_location"):
            preview = self.path(metadata["preview_location"])
            if preview not in paths:
                paths.append(preview)
        return paths
