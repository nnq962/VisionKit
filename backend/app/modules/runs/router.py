"""API tạo lượt chạy ảnh, lấy trạng thái/kết quả và nhận sự kiện mới nhất."""

import asyncio
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from app.core.errors import SourceError

from .schemas import (
    LiveRunCreate,
    RunOptions,
    RunRecord,
    StreamRunCreate,
    WebcamCheckRequest,
    WebcamRunCreate,
    YoutubeRunCreate,
)
from .service import RunService

router = APIRouter(prefix="/runs", tags=["runs"])


# ------------------------------ Lấy service chạy -----------------------------
def get_service(request: Request) -> RunService:
    """Lấy service đang sống trong app, không mở thêm kết nối hoặc nạp model."""
    return request.app.state.runs


# ------------------------- Kiểm webcam trên máy AI ----------------------------
@router.post("/webcam/check")
async def check_webcam(
    body: WebcamCheckRequest, service: Annotated[RunService, Depends(get_service)]
) -> dict:
    """Proxy kiểm webcam local, không khởi chạy model hay mở camera từ backend."""
    if not service.settings.ai_url:
        raise SourceError(503, "AI chưa được cấu hình.")
    try:
        response = await service.client.post(
            f"{service.settings.ai_url}/api/v1/webcams/check",
            json=body.model_dump(),
            timeout=25,
        )
        if response.status_code != 200:
            detail = response.json().get("detail")
            raise SourceError(
                422,
                detail if isinstance(detail, str) else "Không kiểm tra được webcam.",
            )
        return response.json()
    except SourceError:
        raise
    except Exception:
        raise SourceError(503, "Không kết nối được AI để kiểm tra webcam.") from None


# ---------------------------- Chạy webcam local -------------------------------
@router.post("/webcam", response_model=RunRecord, status_code=202)
async def create_webcam_run(
    body: WebcamRunCreate, service: Annotated[RunService, Depends(get_service)]
) -> RunRecord:
    """YOLO mở đúng device index local; không tạo path MediaMTX hoặc video snapshot."""
    return await service.create_webcam(
        body.model_id, body.options, body.device_index, body.duration_seconds
    )


# ------------------------- AI video YouTube đã chuẩn bị -----------------------
@router.post("/youtube", response_model=RunRecord, status_code=202)
async def create_youtube_run(
    body: YoutubeRunCreate,
    request: Request,
    service: Annotated[RunService, Depends(get_service)],
) -> RunRecord:
    """Snapshot file cache đã xác minh; xoá job YouTube sau đó không ngắt run."""
    path = request.app.state.youtube.content(body.session_id.hex)
    with path.open("rb") as stream:
        return await service.create(
            body.model_id, body.options, stream, "youtube.mp4", "video"
        )


# --------------------------- AI camera qua relay -----------------------------
@router.post("/live", response_model=RunRecord, status_code=202)
async def create_live_run(
    body: LiveRunCreate, service: Annotated[RunService, Depends(get_service)]
) -> RunRecord:
    """Chạy MediaMTX path của camera đã lưu hoặc preview tạm; video không qua Python."""
    return await service.create_live(
        body.model_id,
        body.options,
        str(body.source_id) if body.source_id else None,
        str(body.preview_id) if body.preview_id else None,
        body.duration_seconds,
    )


# ----------------------------- Chạy nguồn RTSP -------------------------------
@router.post("/stream", response_model=RunRecord, status_code=202)
async def create_stream_run(
    body: StreamRunCreate,
    request: Request,
    service: Annotated[RunService, Depends(get_service)],
) -> RunRecord:
    """Tạo job RTSP có thời hạn từ source đã lưu; không trả URL/password camera."""
    source = request.app.state.sources.get(str(body.source_id))
    return await service.create_stream(
        body.model_id, body.options, source, body.duration_seconds
    )


# ------------------------------ Tạo lượt chạy ảnh ----------------------------
@router.post("", response_model=RunRecord, status_code=202)
async def create_run(
    service: Annotated[RunService, Depends(get_service)],
    model_id: Annotated[str, Form()],
    options: Annotated[str, Form()],
    file: Annotated[UploadFile | None, File()] = None,
    source_id: Annotated[UUID | None, Form()] = None,
    request: Request = None,
    kind: Annotated[Literal["image", "screen", "video"], Form()] = "image",
) -> RunRecord:
    """Nhận model/thông số và đúng một ảnh upload hoặc source ID đã lưu, trả job 202."""
    try:
        parsed = RunOptions.model_validate_json(options)
    except ValidationError as error:
        raise SourceError(422, "Thông số chạy chưa hợp lệ.") from error
    if (file is None) == (source_id is None):
        raise SourceError(422, "Chọn một ảnh upload hoặc một source đã lưu.")
    if file:
        try:
            return await service.create(
                model_id, parsed, file.file, file.filename or "image", kind
            )
        finally:
            file.file.close()
    sources = request.app.state.sources
    if sources.get(str(source_id)).kind.value == "stream":
        raise SourceError(422, "Chạy source RTSP bằng POST /api/v1/runs/stream.")
    source, path = sources.content(str(source_id))
    if source.kind.value not in {"image", "screen", "video"}:
        raise SourceError(422, "Hiện hỗ trợ inference ảnh, ảnh màn hình và video file.")
    with path.open("rb") as stream:
        return await service.create(
            model_id,
            parsed,
            stream,
            source.metadata.get("original_filename", path.name),
            source.kind.value,
        )


# ------------------------------ Chi tiết lượt chạy ---------------------------
@router.get("/{run_id}", response_model=RunRecord)
def get_run(
    run_id: UUID, service: Annotated[RunService, Depends(get_service)]
) -> RunRecord:
    """Trả trạng thái và JSON kết quả hiện tại để tải lại hoặc fallback khi WebSocket lỗi."""
    return service.get(str(run_id))


# ------------------------------ Dừng lượt chạy -------------------------------
@router.delete("/{run_id}", response_model=RunRecord)
async def cancel_run(
    run_id: UUID, service: Annotated[RunService, Depends(get_service)]
) -> RunRecord:
    """Huỷ inference active; trả trạng thái cuối, không xoá kết quả đã hoàn tất."""
    return await service.cancel(str(run_id))


# --------------------------- Hoàn thành và dọn lượt ---------------------------
@router.delete("/{run_id}/resources", status_code=204)
async def finish_run(
    run_id: UUID, service: Annotated[RunService, Depends(get_service)]
) -> Response:
    """Thu hồi worker/snapshot/frame cache và JSON của lượt, giữ nguyên dữ liệu thư viện."""
    await service.finish(str(run_id))
    return Response(status_code=204)


# ------------------------------ Ảnh lượt chạy --------------------------------
@router.get("/{run_id}/preview", response_model=None)
def preview(
    run_id: UUID, service: Annotated[RunService, Depends(get_service)]
) -> FileResponse | Response:
    """Trả preview gốc hoặc JPEG sidecar để canvas vẽ kết quả theo cùng chiều ảnh."""
    if service.get(str(run_id)).source_kind == "webcam":
        return Response(
            service.webcam_frame(str(run_id)),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )
    return FileResponse(
        service.content(str(run_id)), headers={"Cache-Control": "no-store"}
    )


# ------------------------------ Sự kiện lượt chạy ----------------------------
@router.websocket("/{run_id}/events")
async def events(websocket: WebSocket, run_id: UUID) -> None:
    """Gửi snapshot mới nhất khi trạng thái đổi, không xếp hàng các frame cũ; kiểm tra Origin."""
    service = websocket.app.state.runs
    if websocket.headers.get("origin") not in service.settings.cors_origins:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    previous = ""
    try:
        while True:
            record = service.get(str(run_id))
            current = record.model_dump_json()
            if current != previous:
                await websocket.send_json(record.model_dump(mode="json"))
                previous = current
            if record.status in {"completed", "failed", "cancelled"}:
                await websocket.close()
                return
            try:
                await asyncio.wait_for(websocket.receive_text(), 0.05)
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, SourceError):
        return
