"""Gom các API có phiên bản dưới tiền tố /api/v1."""

from fastapi import APIRouter

from app.modules.logs.router import router as logs_router
from app.modules.models.router import router as models_router
from app.modules.runs.router import router as runs_router
from app.modules.sources.router import router as sources_router
from app.modules.streams.router import router as streams_router

router = APIRouter(prefix="/api/v1")
router.include_router(logs_router)
router.include_router(sources_router)
router.include_router(models_router)
router.include_router(runs_router)
router.include_router(streams_router)


# ---------------------------- Kiểm tra hoạt động -----------------------------
@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Trả trạng thái hoạt động của API; không kết nối camera hoặc chạy AI."""
    return {"status": "ok"}
