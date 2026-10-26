"""API danh mục model, tải nền và quản lý thư viện weights."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.errors import SourceError

from .catalog.ultralytics import CATALOG
from .schemas import (
    DownloadJob,
    DownloadRequest,
    ModelConfiguration,
    ModelSave,
    StoredModel,
)
from .service import ModelService

router = APIRouter(prefix="/models", tags=["models"])


# ----------------------------- Lấy service model -----------------------------
def get_service(request: Request) -> ModelService:
    """Lấy ModelService từ app hiện tại; không tạo HTTP client hay task mới."""
    return request.app.state.models


Service = Annotated[ModelService, Depends(get_service)]


# ------------------------------ Danh mục model -------------------------------
@router.get("/catalog")
def catalog(service: Service) -> dict:
    """Trả danh mục đã ghim release/size/checksum; không gọi mạng mỗi lần mở trang."""
    return {**CATALOG, "max_upload_bytes": service.max_upload_bytes}


# ------------------------------- Upload model --------------------------------
@router.post("/upload", response_model=StoredModel, status_code=201)
async def upload_model(
    service: Service,
    file: Annotated[UploadFile, File()],
    family: Annotated[Literal["yolo", "yoloe"] | None, Form()] = None,
    task: Annotated[
        Literal["detect", "segment", "pose", "classify", "obb"] | None, Form()
    ] = None,
    name: Annotated[str | None, Form()] = None,
) -> StoredModel:
    """Nhận file .pt/.onnx, family/task/name; lưu file và metadata rồi trả model UUID.

    Chỉ kiểm tra đuôi, dung lượng và checksum, không chạy hoặc giải mã weights.
    Luôn đóng file upload; trả lỗi 413/415/422 khi dữ liệu không đáp ứng hợp đồng.
    """
    try:
        model = await run_in_threadpool(
            service.upload, file.file, file.filename or "", name, family, task
        )
        return service.inspector.start(model)
    finally:
        file.file.close()


# ----------------------------- Upload model tạm ------------------------------
@router.post("/temporary", response_model=StoredModel, status_code=201)
async def upload_temporary(
    service: Service,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
) -> StoredModel:
    """Lưu file tạm 24 giờ và tự đọc metadata; chưa thêm vào danh sách thư viện.

    Trả model ID dùng chung cho inspect/pipeline/save. Dùng giới hạn upload
    và rollback như upload thường; luôn đóng multipart sau khi lưu file.
    """
    try:
        model = await run_in_threadpool(
            service.upload, file.file, file.filename or "", name, None, None, True
        )
        return service.inspector.start(model)
    finally:
        file.file.close()


# ------------------------------- Lưu model tạm -------------------------------
@router.post("/{model_id}/save", response_model=StoredModel)
async def save_temporary(
    model_id: str, body: ModelSave, service: Service
) -> StoredModel:
    """Chuyển model tạm còn hiệu lực vào thư viện; không upload/load lại file hoặc mất metadata."""
    return await service.promote(model_id, body.name)


# ------------------------------- Tạo lượt tải --------------------------------
@router.post("/downloads", response_model=DownloadJob, status_code=202)
async def start_download(body: DownloadRequest, service: Service) -> DownloadJob:
    """Nhận catalog_id, trả 202 cùng job; lỗi 404/409/413/429 nếu không thể bắt đầu."""
    return await service.start(body.catalog_id)


# ---------------------------- Danh sách lượt tải -----------------------------
@router.get("/downloads")
def downloads(service: Service) -> dict[str, list[DownloadJob]]:
    """Trả lượt active và lịch sử gần nhất để khôi phục theo dõi khi reload trang."""
    return {"items": service.repository.jobs()}


# ----------------------------- Chi tiết lượt tải -----------------------------
@router.get("/downloads/{job_id}", response_model=DownloadJob)
def download_status(job_id: UUID, service: Service) -> DownloadJob:
    """Trả số byte, phần trăm và lỗi của job_id; 404 nếu không tồn tại."""
    return service.get_job(str(job_id))


# ------------------------------- Huỷ lượt tải --------------------------------
@router.delete("/downloads/{job_id}", response_model=DownloadJob)
async def cancel_download(job_id: UUID, service: Service) -> DownloadJob:
    """Huỷ job active và dọn file tạm; trả trạng thái sau khi thao tác hoàn tất."""
    return await service.cancel(str(job_id))


# ------------------------------ Thư viện model -------------------------------
@router.get("")
def models(service: Service) -> dict[str, list[StoredModel]]:
    """Liệt kê weights đã tải hoàn chỉnh; không load model hoặc truy cập GPU."""
    return {"items": service.repository.models()}


# ------------------------------ Chi tiết model -------------------------------
@router.get("/{model_id}", response_model=StoredModel)
def get_model(model_id: str, service: Service) -> StoredModel:
    """Đọc metadata model_id đã lưu; SourceError 404 khi không có trong thư viện."""
    return service.available(model_id)


# ----------------------------- Đọc lại metadata ------------------------------
@router.post("/{model_id}/inspect", response_model=StoredModel, status_code=202)
async def inspect_model(model_id: str, service: Service) -> StoredModel:
    """Tạo hoặc lấy lượt inspect đang chạy; trả ngay trạng thái để web theo dõi."""
    return service.inspector.start(service.available(model_id))


# ----------------------------- Bổ sung metadata ------------------------------
@router.patch("/{model_id}/metadata", response_model=StoredModel)
def configure_model(
    model_id: str, body: ModelConfiguration, service: Service
) -> StoredModel:
    """Nhận khai báo thủ công khi thiếu metadata/AI offline; không ghi đè lượt đang kiểm tra."""
    model = service.available(model_id)
    if model.inspection.status in {"queued", "processing", "failed"}:
        raise SourceError(
            409, "Không thể khai báo khi đang đọc metadata hoặc file không đọc được."
        )
    if body.family == "yoloe" and body.task != "segment":
        raise SourceError(422, "YOLOE dùng tác vụ Segmentation.")
    return service.repository.configure(model_id, body.family, body.task)


# --------------------------------- Xoá model ---------------------------------
@router.delete("/{model_id}", status_code=204)
async def delete_model(model_id: str, service: Service) -> Response:
    """Xoá metadata và file weights của model_id; 404 nếu model chưa được lưu."""
    await service.delete(model_id)
    return Response(status_code=204)
