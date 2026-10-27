"""API job YouTube tạm, preview dạng file và huỷ download."""

from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/youtube", tags=["youtube"])


# ---------------------------- Yêu cầu liên kết video --------------------------
class YoutubeCreate(BaseModel):
    """Nhận đúng một URL video YouTube; canonical hoá tại service."""

    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=2048)


# ------------------------------- Tạo job video -------------------------------
@router.post("/sessions", status_code=202)
async def create_session(body: YoutubeCreate, request: Request) -> dict:
    """Trả queued ngay; download chạy trong worker có timeout và giới hạn dung lượng."""
    return request.app.state.youtube.create(body.url)


# ------------------------------ Theo dõi job video ----------------------------
@router.get("/sessions/{session_id}")
def get_session(session_id: UUID, request: Request) -> dict:
    """Trả trạng thái chuẩn bị, metadata và gia hạn cache một giờ."""
    service = request.app.state.youtube
    return service.response(service.get(session_id.hex))


# ------------------------------- Xem video tạm --------------------------------
@router.get("/sessions/{session_id}/content")
def content(session_id: UUID, request: Request) -> FileResponse:
    """Phục vụ MP4 đã xác minh, hỗ trợ Range để tua video."""
    return FileResponse(
        request.app.state.youtube.content(session_id.hex),
        media_type="video/mp4",
        headers={"Cache-Control": "no-store"},
    )


# ----------------------------- Thumbnail video tạm ----------------------------
@router.get("/sessions/{session_id}/thumbnail")
def thumbnail(session_id: UUID, request: Request) -> FileResponse:
    """Trả JPEG của video đã xác minh, không truy cập thumbnail URL bên ngoài."""
    return FileResponse(
        request.app.state.youtube.content(session_id.hex, thumbnail=True),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


# ------------------------------ Huỷ và xoá video ------------------------------
@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: UUID, request: Request) -> Response:
    """Đợi reap download trước khi xoá cache; idempotent khi phiên không còn."""
    await request.app.state.youtube.delete(session_id.hex)
    return Response(status_code=204)
