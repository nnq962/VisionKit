"""API nội bộ của VisionKit AI để backend yêu cầu đọc metadata model."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing, suppress

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.contracts.model import InspectRequest, InspectResult
from app.contracts.prediction import PredictRequest
from app.core.config import Settings, load_settings
from app.inference.service import InferenceService
from app.inspection.service import InspectionService


# ------------------------------ Khởi tạo API AI ------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    """Tạo app và service inspect dùng settings; không mở DB hoặc load weights khi startup."""
    application = FastAPI(title="VisionKit AI", version="0.1.0")
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
                yield json.dumps({"type": "error", "error": str(error)[:250]}) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson")

    return application


app = create_app()
