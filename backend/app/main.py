"""Entry point FastAPI quản lý dữ liệu VisionKit, độc lập với module AI."""

import asyncio
import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import router
from app.core.config import Settings, load_settings
from app.core.errors import SourceError
from app.core.logs import LogBuffer, attach_logging, detach_logging
from app.db import initialize_database
from app.modules.logs.service import LogCollector
from app.modules.models.repository import ModelRepository
from app.modules.models.service import ModelService
from app.modules.runs.repository import RunRepository
from app.modules.runs.service import RunService
from app.modules.sources.repository import SourceRepository
from app.modules.sources.service import SourceService
from app.storage.local import LocalStorage

logger = logging.getLogger(__name__)


# ----------------------------- Khởi tạo FastAPI ------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    """Tạo FastAPI với cấu hình được truyền vào hoặc đọc từ môi trường.

    Vòng đời startup tạo storage và áp dụng migration SQLite trước khi nhận
    request. Không khởi tạo AI. Cho phép truyền Settings riêng để test không
    chạm dữ liệu thật. Trả app có router API, CORS và xử lý lỗi nghiệp vụ.
    """
    config = settings or load_settings()

    # ----------------------------- Vòng đời ứng dụng -----------------------------
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Khởi tạo DB/service một lần khi chạy app; các kết nối DB tự đóng theo thao tác."""
        application.state.logs = LogBuffer("backend")
        async with AsyncExitStack() as cleanup:
            attached = attach_logging(application.state.logs)
            cleanup.callback(detach_logging, attached)
            collector = LogCollector(application.state.logs, config.ai_url)
            cleanup.push_async_callback(collector.close)
            application.state.log_collector = collector
            collector_task = asyncio.create_task(collector.run())
            cleanup.push_async_callback(cancel_background_task, collector_task)
            database = initialize_database(config.database_path)
            application.state.sources = SourceService(
                SourceRepository(database), LocalStorage(config)
            )
            application.state.models = ModelService(ModelRepository(database), config)
            cleanup.push_async_callback(application.state.models.shutdown)
            await application.state.models.cleanup_temporary()
            application.state.models.cleanup_task = asyncio.create_task(
                application.state.models.maintain_temporary()
            )
            application.state.runs = RunService(
                RunRepository(database), application.state.models, config
            )
            cleanup.push_async_callback(application.state.runs.shutdown)
            application.state.runs.cleanup_task = asyncio.create_task(
                application.state.runs.maintain()
            )
            logger.info("Backend đã sẵn sàng.")
            yield

    application = FastAPI(title="VisionKit API", version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    application.include_router(router)
    application.add_exception_handler(SourceError, source_error_handler)
    application.add_exception_handler(sqlite3.Error, storage_error_handler)
    application.add_exception_handler(OSError, storage_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    return application


# --------------------------- Lỗi kiểm tra đầu vào ----------------------------
async def validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    """Trả vị trí/loại lỗi mà không phản chiếu input có thể chứa mật khẩu camera."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {
                    "loc": list(item["loc"]),
                    "type": item["type"],
                    "msg": "Giá trị không hợp lệ.",
                }
                for item in error.errors()
            ]
        },
    )


# ---------------------------- Xử lý lỗi nghiệp vụ ----------------------------
async def source_error_handler(request: Request, error: SourceError) -> JSONResponse:
    """Chuyển lỗi nghiệp vụ thành JSON detail và mã HTTP đã xác định."""
    return JSONResponse(
        status_code=error.status_code, content={"detail": error.message}
    )


# ----------------------------- Xử lý lỗi lưu trữ -----------------------------
async def storage_error_handler(request: Request, error: Exception) -> JSONResponse:
    """Ghi lỗi lưu trữ vào log và trả thông báo 503, không lộ đường dẫn nội bộ."""
    logger.error("Source storage operation failed", exc_info=error)
    return JSONResponse(
        status_code=503,
        content={"detail": "Không thể truy cập dữ liệu. Vui lòng thử lại."},
    )


# -------------------------------- Huỷ task nền -------------------------------
async def cancel_background_task(task: asyncio.Task) -> None:
    """Huỷ task nền và đợi kết thúc trước khi đóng tài nguyên mà task sử dụng."""
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


app = create_app()
