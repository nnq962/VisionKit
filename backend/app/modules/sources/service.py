"""Điều phối lưu ảnh/video và metadata; không chứa xử lý AI."""

from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.errors import SourceError
from app.storage.local import LocalStorage

from .models import Source, SourceKind
from .repository import SourceRepository
from .schemas import SourcePage, SourceResponse


# ------------------------------ Service source -------------------------------
class SourceService:
    """Phối hợp repository và storage cho vòng đời source ảnh/video.

    Thuộc tính:
        repository: Lớp đọc/ghi thông tin source trong SQLite.
        storage: Lớp lưu file media trên máy backend.
    """

    def __init__(self, repository: SourceRepository, storage: LocalStorage) -> None:
        """Nhận repository và storage dùng chung; không mở kết nối DB mới."""
        self.repository = repository
        self.storage = storage

    def response(self, source: Source) -> SourceResponse:
        """Chuyển bản ghi thành response, thêm URL nội dung cho source đã upload."""
        response = SourceResponse.model_validate(source)
        if source.kind in (SourceKind.IMAGE, SourceKind.SCREEN, SourceKind.VIDEO):
            response.content_url = f"/api/v1/sources/{source.id}/content"
            response.preview_url = (
                f"/api/v1/sources/{source.id}/preview"
                if source.metadata.get("preview_location")
                else response.content_url
            )
        return response

    def get(self, source_id: str) -> Source:
        """Trả bản ghi theo ID; phát sinh SourceError 404 nếu không tồn tại."""
        source = self.repository.get(source_id)
        if source is None:
            raise SourceError(404, "Không tìm thấy source.")
        return source

    def inspect(self, stream: BinaryIO) -> tuple[dict, bytes]:
        """Trả metadata và JPEG tạm để preview; không lưu bản ghi vào thư viện.

        Nhận stream upload nhị phân và chuyển cho storage kiểm tra. SourceError
        báo file lỗi/quá giới hạn; file tạm được dọn sau khi tạo preview.
        """
        return self.storage.inspect(stream)

    def upload(
        self, stream: BinaryIO, filename: str, name: str | None, kind: SourceKind
    ) -> SourceResponse:
        """Lưu file và bản ghi; xoá file vừa tạo nếu ghi SQLite thất bại.

        Tham số:
            stream: File nhị phân lấy từ multipart upload.
            filename: Tên file gốc; chỉ dùng hiển thị metadata.
            name: Tên hiển thị tuỳ chọn, tối đa 120 ký tự.
            kind: IMAGE, VIDEO hoặc SCREEN, được kiểm tra tại router.
        Trả về:
            Source đã lưu cùng URL preview.
        Ngoại lệ:
            SourceError: Tên rỗng, loại không phù hợp, file lỗi hoặc quá giới hạn.
        """
        title = (
            name.strip()
            if name is not None
            else Path(filename.replace("\\", "/")).name[:120]
        )
        if not title or len(title) > 120:
            raise SourceError(422, "Tên source phải có từ 1 đến 120 ký tự.")
        if kind not in (SourceKind.IMAGE, SourceKind.SCREEN, SourceKind.VIDEO):
            raise SourceError(
                422, "Hiện chỉ hỗ trợ lưu ảnh, video và ảnh chụp màn hình."
            )
        if kind == SourceKind.VIDEO:
            location, metadata = self.storage.save_video(stream, filename)
        else:
            location, metadata = self.storage.save_image(stream, filename)
        try:
            source = self.repository.create(
                name=title, kind=kind, location=location, metadata=metadata
            )
        except Exception:
            for path in self.storage.source_paths(location, metadata):
                path.unlink(missing_ok=True)
            raise
        return self.response(source)

    def list(
        self, kind: SourceKind | None, limit: int, offset: int, q: str = ""
    ) -> SourcePage:
        """Trả trang mới nhất và tổng khớp kind/q với giới hạn limit, vị trí offset."""
        return SourcePage(
            items=[
                self.response(item)
                for item in self.repository.list(
                    kind=kind, limit=limit, offset=offset, q=q
                )
            ],
            total=self.repository.count(kind=kind, q=q),
            limit=limit,
            offset=offset,
        )

    def rename(self, source_id: str, name: str) -> SourceResponse:
        """Đổi tên source đã tồn tại; trả 404 nếu bản ghi đã bị xoá."""
        updated = self.repository.update(source_id, name=name)
        if updated is None:
            raise SourceError(404, "Không tìm thấy source.")
        return self.response(updated)

    def content(self, source_id: str, preview: bool = False) -> tuple[Source, Path]:
        """Trả bản ghi và đường dẫn file gốc hoặc preview JPEG.

        Tham số:
            source_id: UUID của source cần lấy nội dung.
            preview: True chọn sidecar JPEG nếu có; mặc định lấy file gốc.
        Ngoại lệ:
            SourceError: 404 nếu source sai loại, không tồn tại hoặc file đã mất.
        """
        source = self.get(source_id)
        if source.kind not in (SourceKind.IMAGE, SourceKind.SCREEN, SourceKind.VIDEO):
            raise SourceError(404, "Source này không có nội dung đã lưu.")
        location = (
            source.metadata.get("preview_location", source.location)
            if preview
            else source.location
        )
        path = self.storage.path(location)
        if not path.is_file():
            raise SourceError(404, "File của source không còn tồn tại.")
        return source, path

    def delete(self, source_id: str) -> None:
        """Xoá bản ghi và file media thuộc storage; không xoá file ngoài storage.

        File được đổi tên tạm trước khi xoá DB và khôi phục nếu DB báo lỗi.
        Nếu file đã mất, vẫn cho phép xoá metadata. SourceError 404 báo ID lạ;
        OSError hoặc lỗi SQLite báo thao tác lưu trữ không hoàn tất.
        """
        source = self.get(source_id)
        paths = (
            self.storage.source_paths(source.location, source.metadata)
            if source.kind in (SourceKind.IMAGE, SourceKind.SCREEN, SourceKind.VIDEO)
            else []
        )
        staged: list[tuple[Path, Path]] = []
        try:
            for path in paths:
                if path.is_file():
                    temporary = path.with_name(f"{uuid4().hex}.trash")
                    path.replace(temporary)
                    staged.append((path, temporary))
            deleted = self.repository.delete(source_id)
        except Exception:
            for original, temporary in reversed(staged):
                temporary.replace(original)
            raise
        for _, temporary in staged:
            temporary.unlink(missing_ok=True)
        if not deleted:
            raise SourceError(404, "Không tìm thấy source.")
