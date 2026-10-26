"""API lease, trạng thái camera và WHEP signaling; video đi trực tiếp qua WebRTC."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.errors import SourceError
from app.modules.streams.schemas import TemporaryPreviewCreate
from app.modules.streams.service import PreviewService

router = APIRouter(prefix="/streams", tags=["streams"])


# ----------------------------- Service preview -------------------------------
def get_service(request: Request) -> PreviewService:
    """Trả registry lease dùng chung của ứng dụng hiện tại."""
    return request.app.state.streams


Service = Annotated[PreviewService, Depends(get_service)]


# --------------------------- Kiểm tra RTSP tạm -------------------------------
@router.post("/temporary/sessions", status_code=201)
async def create_temporary_session(
    body: TemporaryPreviewCreate, service: Service
) -> dict:
    """Nhận URL chưa lưu, tạo lease để kiểm tra MediaMTX và phát WHEP nếu đọc được."""
    return await service.create_temporary(
        str(body.preview_id), body.url.get_secret_value()
    )


# ----------------------------- Tạo phiên WebRTC ------------------------------
@router.post("/{source_id}/sessions", status_code=201)
async def create_session(source_id: UUID, service: Service) -> dict:
    """Mở path camera đã lưu; trả ID lease và URL signaling không có credentials."""
    return await service.create(str(source_id))


# ----------------------------- Trạng thái camera -----------------------------
@router.get("/sessions/{token}")
async def status(token: UUID, service: Service) -> dict:
    """Gia hạn lease và trả trạng thái/xác thực được MediaMTX báo cáo."""
    return await service.status(str(token))


# ------------------------------ Offer SDP WHEP -------------------------------
@router.post("/sessions/{token}/whep")
async def offer(token: UUID, request: Request, service: Service) -> Response:
    """Nhận SDP tối đa 256 KiB và proxy qua MediaMTX; không proxy RTP/video."""
    if request.headers.get("content-type", "").split(";")[0] != "application/sdp":
        raise SourceError(415, "Yêu cầu SDP WebRTC.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 256 * 1024:
            raise SourceError(413, "SDP vượt giới hạn.")
    try:
        sdp = body.decode("utf-8")
    except UnicodeDecodeError:
        raise SourceError(422, "SDP không hợp lệ.") from None
    answer = await service.offer(str(token), sdp)
    return Response(
        answer, media_type="application/sdp", headers={"Cache-Control": "no-store"}
    )


# ------------------------------- Dừng WebRTC ---------------------------------
@router.delete("/sessions/{token}", status_code=204)
async def close_session(token: UUID, service: Service) -> Response:
    """Đóng WHEP và nhả camera khi không còn viewer; idempotent."""
    await service.close(str(token))
    return Response(status_code=204)
