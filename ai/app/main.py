"""API nội bộ của VisionKit AI để backend yêu cầu đọc metadata model."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import aclosing, asynccontextmanager, suppress
from typing import Annotated, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from app.contracts.model import InspectRequest, InspectResult
from app.contracts.prediction import PredictRequest
from app.core.config import Settings, load_settings
from app.core.logs import (
    LogBuffer,
    LogPage,
    attach_logging,
    detach_logging,
    run_context,
)
from app.inference.service import InferenceService
from app.inspection.service import InspectionService

logger = logging.getLogger(__name__)


# ------------------------------ Khởi tạo API AI ------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    """Tạo app và service inspect dùng settings; không mở DB hoặc load weights khi startup."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Cài log theo vòng đời API; khôi phục handler khi shutdown hoặc test đóng app."""
        attached = attach_logging(application.state.logs)
        try:
            logger.info("AI API đã sẵn sàng; model được nạp khi có yêu cầu.")
            yield
        finally:
            detach_logging(attached)

    application = FastAPI(title="VisionKit AI", version="0.1.0", lifespan=lifespan)
    application.state.logs = LogBuffer("ai")

    @application.middleware("http")
    async def request_logging(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Gắn UUID lượt chạy vào context; ghi lỗi/request nghiệp vụ, bỏ health và logs."""
        run_id = None
        header = request.headers.get("X-VisionKit-Run-ID")
        if header:
            try:
                run_id = str(UUID(header))
            except ValueError:
                return JSONResponse(
                    status_code=422, content={"detail": "Run ID không hợp lệ."}
                )
        token = run_context.set(run_id)
        quiet = request.url.path in {"/api/v1/logs", "/api/v1/health"}
        try:
            if not quiet:
                logger.info("Nhận %s %s.", request.method, request.url.path)
            response = await call_next(request)
            if response.status_code >= 400 and not quiet:
                logger.warning(
                    "Yêu cầu %s trả HTTP %s.", request.url.path, response.status_code
                )
            return response
        except Exception:
            if not quiet:
                logger.exception("Yêu cầu AI thất bại.")
            raise
        finally:
            run_context.reset(token)

    @application.get("/api/v1/logs", response_model=LogPage, tags=["logs"])
    def read_logs(
        response: Response,
        after: Annotated[str | None, Query(max_length=64)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
        min_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
        run_id: UUID | None = None,
    ) -> LogPage:
        """Cung cấp log RAM cho backend thu nội bộ; cursor sai trả 422, không cache."""
        response.headers["Cache-Control"] = "no-store"
        try:
            return application.state.logs.read(
                after,
                limit,
                min_level=min_level,
                run_id=str(run_id) if run_id else None,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    service = InspectionService(settings or load_settings())
    application.state.inspection = service
    inference = InferenceService(settings or load_settings())

    @application.get("/api/v1/health")
    def health() -> dict[str, str]:
        """Trả trạng thái API nội bộ sẵn sàng nhận yêu cầu, không chạy inference."""
        return {"status": "ok"}

    @application.post("/api/v1/models/inspect", response_model=InspectResult)
    async def inspect_model(request: InspectRequest) -> InspectResult:
        """Nhận location tương đối/checksum từ backend và trả metadata đọc thực tế."""
        return await service.inspect(request)

    @application.post("/api/v1/inference/image")
    async def predict_image(body: PredictRequest, request: Request) -> dict:
        """Chạy ảnh và theo dõi client disconnect để huỷ worker nếu backend huỷ lượt chạy."""
        task = asyncio.create_task(inference.predict(body))
        try:
            while not task.done():
                if await request.is_disconnected():
                    task.cancel()
                    raise HTTPException(499, "Client đã ngắt kết nối.")
                await asyncio.sleep(0.1)
            return await task
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    @application.post("/api/v1/inference/video")
    async def predict_video(body: PredictRequest) -> StreamingResponse:
        """Trả NDJSON frame/terminal; ASGI disconnect huỷ generator và worker video."""

        async def stream() -> AsyncIterator[str]:
            """Chuyển event service thành một dòng JSON; lỗi giữa luồng có event error."""
            try:
                async with aclosing(inference.video(body)) as events:
                    async for event in events:
                        yield json.dumps(event, allow_nan=False) + "\n"
            except ValueError as error:
                logger.warning("Inference video thất bại: %s", error)
                yield json.dumps({"type": "error", "error": str(error)[:250]}) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return application


app = create_app()
