"""API nội bộ của VisionKit AI để backend yêu cầu đọc metadata model."""

from fastapi import FastAPI

from app.contracts.model import InspectRequest, InspectResult
from app.core.config import Settings, load_settings
from app.inspection.service import InspectionService


# ------------------------------ Khởi tạo API AI ------------------------------
def create_app(settings: Settings | None = None) -> FastAPI:
    """Tạo app và service inspect dùng settings; không mở DB hoặc load weights khi startup."""
    application = FastAPI(title="VisionKit AI", version="0.1.0")
    service = InspectionService(settings or load_settings())
    application.state.inspection = service

    @application.get("/api/v1/health")
    def health() -> dict[str, str]:
        """Trả trạng thái API nội bộ sẵn sàng nhận yêu cầu, không chạy inference."""
        return {"status": "ok"}

    @application.post("/api/v1/models/inspect", response_model=InspectResult)
    async def inspect_model(request: InspectRequest) -> InspectResult:
        """Nhận location tương đối/checksum từ backend và trả metadata đọc thực tế."""
        return await service.inspect(request)

    return application


app = create_app()
