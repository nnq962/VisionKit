"""HTTP API quản lý ảnh, video và ảnh chụp màn hình đã lưu."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import get_source_service
from app.core.errors import SourceError

from .models import SourceKind
from .schemas import RtspSourceCreate, SourcePage, SourceRename, SourceResponse
from .service import SourceService

router = APIRouter(prefix="/sources", tags=["sources"])
Service = Annotated[SourceService, Depends(get_source_service)]


# ------------------------------ Tạo nguồn RTSP -------------------------------
@router.post("/rtsp", response_model=SourceResponse, status_code=201)
def create_rtsp(body: RtspSourceCreate, service: Service) -> SourceResponse:
    """Lưu cấu hình RTSP/RTSPS; response không chứa password hoặc query token."""
    return service.create_rtsp(body)


# ------------------------------ Sửa nguồn RTSP -------------------------------
@router.put("/{source_id}/rtsp", response_model=SourceResponse)
async def update_rtsp(
    source_id: UUID, body: RtspSourceCreate, service: Service, request: Request
) -> SourceResponse:
    """Lưu cấu hình camera và khởi động lại preview, không đổi inference đang chạy."""
    async with request.app.state.streams.lock:
        if request.app.state.streams.inference_active(str(source_id)):
            raise SourceError(409, "Dừng AI trước khi thay cấu hình camera.")
        response = service.update_rtsp(str(source_id), body)
    await request.app.state.streams.restart(str(source_id))
    return response


# ---------------------------- Hàm inspect_source -----------------------------
@router.post("/inspect", response_class=Response)
def inspect_source(service: Service, file: Annotated[UploadFile, File()]) -> Response:
    """Nhận ảnh để tạo JPEG preview tạm, không thêm source vào database.

    Trả JPEG cùng header X-Image-Width/Height/Format của ảnh gốc đã xoay đúng.
    File tạm được dọn sau khi xử lý; lỗi ảnh trả 413/415 tương tự upload.
    """
    try:
        metadata, preview = service.inspect(file.file)
        return Response(
            content=preview,
            media_type="image/jpeg",
            headers={
                "X-Image-Width": str(metadata["width"]),
                "X-Image-Height": str(metadata["height"]),
                "X-Image-Format": str(metadata["format"]),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    finally:
        file.file.close()


# -------------------------------- Upload ảnh ---------------------------------
@router.post("/upload", response_model=SourceResponse, status_code=201)
def upload_source(
    service: Service,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    kind: Annotated[Literal["image", "screen", "video"], Form()] = "image",
) -> SourceResponse:
    """Nhận multipart file/name/kind, lưu file thật và trả metadata cùng preview URL.

    Chấp nhận ảnh, video hoặc ảnh chụp màn hình; trả 413 nếu quá giới hạn và 415 nếu
    nội dung file không hợp lệ. Luôn đóng file upload sau khi xử lý.
    """
    try:
        return service.upload(
            file.file, file.filename or "image", name, SourceKind(kind)
        )
    finally:
        file.file.close()


# ----------------------------- Danh sách source ------------------------------
@router.get("", response_model=SourcePage)
def list_sources(
    service: Service,
    kind: SourceKind | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str, Query(max_length=120)] = "",
) -> SourcePage:
    """Liệt kê theo kind, tên q và limit/offset; tên tối đa 120 ký tự, mới nhất trước."""
    return service.list(kind, limit, offset, q)


# ------------------------------ Chi tiết source ------------------------------
@router.get("/{source_id}", response_model=SourceResponse)
def get_source(source_id: UUID, service: Service) -> SourceResponse:
    """Lấy chi tiết source theo UUID; trả 404 nếu ID không có trong database."""
    return service.response(service.get(str(source_id)))


# ------------------------------- Nội dung ảnh --------------------------------
@router.get("/{source_id}/content", response_class=FileResponse)
def get_source_content(source_id: UUID, service: Service) -> FileResponse:
    """Trả file gốc với MIME xác minh từ nội dung, cho phép preview trực tiếp.

    FileResponse hỗ trợ stream file; không nạp toàn bộ file vào bộ nhớ Python.
    Trả 404 nếu bản ghi hoặc file đã bị xoá.
    """
    source, path = service.content(str(source_id))
    return FileResponse(
        path,
        media_type=source.metadata.get("mime_type", "application/octet-stream"),
        filename=source.metadata.get("original_filename", path.name),
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
    )


# -------------------------- Hàm get_source_preview ---------------------------
@router.get("/{source_id}/preview", response_class=FileResponse)
def get_source_preview(source_id: UUID, service: Service) -> FileResponse:
    """Trả thumbnail video, JPEG của HEIC hoặc ảnh gốc với định dạng khác.

    Tham số:
        source_id: UUID của source đã lưu.
        service: Service quản lý dữ liệu/file được inject theo request.
    Ngoại lệ:
        SourceError: 404 nếu source hoặc file preview không tồn tại.
    """
    source, path = service.content(str(source_id), preview=True)
    return FileResponse(
        path,
        media_type=source.metadata.get(
            "preview_mime_type",
            source.metadata.get("mime_type", "application/octet-stream"),
        ),
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


# ------------------------------ Đổi tên source -------------------------------
@router.patch("/{source_id}", response_model=SourceResponse)
def rename_source(
    source_id: UUID, body: SourceRename, service: Service
) -> SourceResponse:
    """Đổi tên bằng JSON name; trả metadata mới hoặc 404 nếu source không còn."""
    return service.rename(str(source_id), body.name)


# -------------------------------- Xoá source ---------------------------------
@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: UUID, service: Service, request: Request
) -> Response:
    """Xoá source và file gốc/preview tương ứng; trả response rỗng khi thành công."""
    async with request.app.state.streams.lock:
        if request.app.state.streams.inference_active(str(source_id)):
            raise SourceError(409, "Dừng AI trước khi xoá camera.")
        service.delete(str(source_id))
    await request.app.state.streams.remove(str(source_id))
    return Response(status_code=204)
