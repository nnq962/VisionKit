"""Đọc log hai dịch vụ từ bộ đệm backend; không gọi AI trong request của web."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response

from .schemas import CombinedLogPage

router = APIRouter(prefix="/logs", tags=["logs"])


# ----------------------------- Đọc log tổng hợp ------------------------------
@router.get("", response_model=CombinedLogPage)
def read_logs(
    request: Request,
    response: Response,
    after: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    service: Literal["backend", "ai"] | None = None,
    min_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    run_id: UUID | None = None,
) -> dict:
    """Trả trang log và trạng thái bộ thu AI; cursor sai trả 422, response không cache.

    Bỏ after khi đổi bộ lọc. API chỉ phản ánh bộ đệm của một worker hiện tại,
    không phải lịch sử log bền vững và không có chức năng thực thi terminal.
    """
    response.headers["Cache-Control"] = "no-store"
    try:
        page = request.app.state.logs.read(
            after, limit, service, min_level, str(run_id) if run_id else None
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {**page.model_dump(), "ai": dict(request.app.state.log_collector.status)}
