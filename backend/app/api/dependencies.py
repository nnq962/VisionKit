"""Dependency lấy service đã khởi tạo trong vòng đời ứng dụng."""

from fastapi import Request

from app.modules.sources.service import SourceService


# ------------------------- Dependency service source -------------------------
def get_source_service(request: Request) -> SourceService:
    """Trả SourceService của ứng dụng hiện tại; không tạo lại storage hoặc DB."""
    return request.app.state.sources
