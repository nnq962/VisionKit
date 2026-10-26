"""Điều phối MediaMTX qua Control API; backend không xử lý frame video."""

import asyncio
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from anyio import CancelScope

from app.core.config import Settings
from app.core.errors import SourceError
from app.core.rtsp import validate_rtsp_url
from app.modules.sources.models import SourceKind
from app.modules.sources.service import SourceService


# ------------------------------- Phiên xem WebRTC ----------------------------
@dataclass
class Viewer:
    """Lease ngẫu nhiên cho một browser viewer, giữ Location WHEP ở server."""

    source_id: str
    expires: float
    upstream: str | None = None
    inference: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


# ----------------------------- Quản lý MediaMTX ------------------------------
class PreviewService:
    """Tạo path/camera dùng chung; lease heartbeat giải phóng nguồn khi hết viewer.

    Thuộc tính:
        viewers: Map token ngẫu nhiên sang phiên xem; không có mật khẩu camera.
        paths: Source ID do instance này đăng ký trên MediaMTX.
    """

    def __init__(self, sources: SourceService, settings: Settings) -> None:
        """Nhận service nguồn và URL MediaMTX nội bộ; chưa kết nối camera."""
        self.sources = sources
        self.settings = settings
        self.api = httpx.AsyncClient(base_url=settings.mediamtx_api_url, timeout=8)
        self.whep = httpx.AsyncClient(base_url=settings.mediamtx_webrtc_url, timeout=15)
        self.viewers: dict[str, Viewer] = {}
        self.paths: set[str] = set()
        self.temporary_urls: dict[str, str] = {}
        self.lock = asyncio.Lock()
        self.closed = False

    def path(self, source_id: str) -> str:
        """Tạo tên path ổn định từ UUID nguồn, không chứa URL hay tài khoản."""
        return f"visionkit_{source_id}"

    async def api_request(
        self, method: str, path: str, **kwargs: object
    ) -> httpx.Response:
        """Gọi API nội bộ; lỗi không phản chiếu response/URL có thể chứa bí mật."""
        try:
            return await self.api.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise SourceError(
                503, "MediaMTX chưa sẵn sàng. Kiểm tra dịch vụ media."
            ) from None

    async def ensure_path(self, source_id: str) -> None:
        """Đăng ký URL RTSP/TCP với MediaMTX; chỉ gọi khi đang giữ lock registry."""
        location = self.temporary_urls.get(source_id)
        if location is None:
            source = self.sources.get(source_id)
            if source.kind != SourceKind.STREAM:
                raise SourceError(422, "Chọn một camera RTSP đã lưu.")
            location = source.location
        try:
            url = validate_rtsp_url(location)
        except ValueError:
            raise SourceError(
                422, "Địa chỉ camera không phải RTSP/RTSPS hợp lệ."
            ) from None
        parsed = urlsplit(url)
        if self.settings.mediamtx_source_host and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            credentials = (
                parsed.netloc.rsplit("@", 1)[0] + "@" if "@" in parsed.netloc else ""
            )
            address = self.settings.mediamtx_source_host
            if parsed.port is not None:
                address += f":{parsed.port}"
            url = urlunsplit(
                (
                    parsed.scheme,
                    credentials + address,
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                )
            )
        response = await self.api_request(
            "POST",
            f"/v3/config/paths/replace/{self.path(source_id)}",
            json={"source": url, "rtspTransport": "tcp", "sourceOnDemand": False},
        )
        if response.status_code == 404:
            response = await self.api_request(
                "POST",
                f"/v3/config/paths/add/{self.path(source_id)}",
                json={"source": url, "rtspTransport": "tcp", "sourceOnDemand": False},
            )
        if not response.is_success:
            raise SourceError(503, "Không cấu hình được nguồn trên MediaMTX.")
        self.paths.add(source_id)

    async def create_viewer(self, source_id: str) -> dict:
        """Tạo lease khi đang giữ lock; nguồn tạm và đã lưu dùng cùng giới hạn path."""
        if self.closed:
            raise SourceError(503, "Dịch vụ preview đang dừng.")
        if source_id not in self.paths:
            if len(self.paths) >= 4:
                raise SourceError(
                    429, "Đã mở tối đa bốn camera. Dừng một camera trước."
                )
            await self.ensure_path(source_id)
        token = str(uuid4())
        self.viewers[token] = Viewer(source_id, time.monotonic() + 45)
        return {"id": token, "whep_url": f"/api/v1/streams/sessions/{token}/whep"}

    async def create(self, source_id: str) -> dict:
        """Tạo lease 45 giây cho camera đã lưu; nhiều browser dùng chung path."""
        async with self.lock:
            return await self.create_viewer(source_id)

    async def create_temporary(self, preview_id: str, url: str) -> dict:
        """Kiểm tra/xem URL qua phiên RAM, không ghi source/URL vào SQLite hoặc file.

        preview_id thuộc namespace riêng, không thể trùng camera đã lưu. URL
        được giữ cho reconnect đến khi lease cuối đóng/hết hạn và path được dọn.
        Giới hạn bốn path dùng chung với camera đã lưu; lỗi tạo không giữ URL rác.
        """
        try:
            url = validate_rtsp_url(url)
        except ValueError:
            raise SourceError(422, "Địa chỉ camera không hợp lệ.") from None
        key = f"temporary_{preview_id}"
        async with self.lock:
            if self.closed:
                raise SourceError(503, "Dịch vụ preview đang dừng.")
            if key not in self.paths and len(self.paths) >= 4:
                raise SourceError(
                    429, "Đã mở tối đa bốn camera. Dừng một camera trước."
                )
            previous = self.temporary_urls.get(key)
            if previous is not None and previous != url:
                raise SourceError(
                    409, "Phiên thử đã đổi URL. Hãy tạo phiên kiểm tra mới."
                )
            self.temporary_urls[key] = url
            try:
                return await self.create_viewer(key)
            except BaseException:
                # POST cấu hình có thể đã tới relay dù HTTP bị huỷ/mất response.
                # Theo dõi path để task maintain retry cleanup nếu API đang lỗi.
                self.paths.add(key)
                with CancelScope(shield=True):
                    await self.drop_path(key)
                raise

    async def acquire_inference(
        self, source_id: str | None, preview_id: str | None
    ) -> tuple[str, str]:
        """Giữ path cho AI độc lập browser, trả lease và URL relay không có mật khẩu camera."""
        key = source_id or f"temporary_{preview_id}"
        async with self.lock:
            if preview_id and key not in self.temporary_urls:
                raise SourceError(
                    410, "Phiên camera đã hết hạn. Kiểm tra RTSP lại trước khi chạy AI."
                )
            if source_id:
                source = self.sources.get(source_id)
                if source.kind != SourceKind.STREAM:
                    raise SourceError(422, "Chọn camera RTSP để chạy AI.")
            session = await self.create_viewer(key)
            token = session["id"]
            self.viewers[token].inference = True
            self.viewers[token].expires = float("inf")
        return token, f"{self.settings.mediamtx_rtsp_url}/{self.path(key)}"

    def inference_active(self, source_id: str) -> bool:
        """Kiểm camera đang có AI giữ path để tránh thay URL giữa lượt suy luận."""
        return any(
            v.source_id == source_id and v.inference for v in self.viewers.values()
        )

    def viewer(self, token: str) -> Viewer:
        """Lấy lease còn hạn và gia hạn heartbeat; 410 yêu cầu browser tạo phiên mới."""
        viewer = self.viewers.get(token)
        if viewer is None or viewer.expires <= time.monotonic():
            raise SourceError(410, "Phiên xem đã hết hạn. Kết nối lại camera.")
        if not viewer.inference:
            viewer.expires = time.monotonic() + 45
        return viewer

    async def status(self, token: str) -> dict:
        """Đọc available/ready và lỗi nguồn thực từ API; phân loại 401/403, không trả raw error.

        available/ready xác nhận MediaMTX đã đọc được luồng, không chứng minh user có mật
        khẩu nếu camera cho phép anonymous. Chỉ auth_failed khi API có bằng chứng.
        """
        viewer = self.viewer(token)
        name = self.path(viewer.source_id)
        response = await self.api_request("GET", f"/v3/paths/get/{name}")
        if response.status_code == 404:
            async with self.lock:
                await self.ensure_path(viewer.source_id)
            return {"status": "connecting", "auth": "unknown", "codecs": []}
        if not response.is_success:
            raise SourceError(503, "Không đọc được trạng thái MediaMTX.")
        data = response.json()
        if data.get("available", data.get("ready", False)):
            codecs = [track.get("codec", "") for track in data.get("tracks2", [])]
            if not codecs:
                codecs = data.get("tracks", [])
            return {"status": "ready", "auth": "accepted", "codecs": codecs}
        static = await self.api_request("GET", f"/v3/paths/static-sources/get/{name}")
        details = static.json() if static.is_success else {}
        error = details.get("lastError") or ""
        if re.search(
            r"\b(401|403)\b|unauthoriz|forbidden|authentication failed", error, re.I
        ):
            return {
                "status": "error",
                "auth": "rejected",
                "code": "auth_failed",
                "retryable": False,
                "codecs": [],
                "message": "Camera từ chối xác thực. Kiểm tra tài khoản và mật khẩu RTSP.",
            }
        return {
            "status": "reconnecting" if error else "connecting",
            "auth": "unknown",
            "codecs": [],
            "message": "Chưa đọc được camera. Đang thử kết nối lại…" if error else None,
        }

    async def offer(self, token: str, sdp: str) -> str:
        """Proxy WHEP SDP tới MediaMTX; chỉ lưu Location cùng origin/path hợp lệ."""
        viewer = self.viewer(token)
        async with viewer.lock:
            await self.close_whep(viewer)
            try:
                response = await self.whep.post(
                    f"/{self.path(viewer.source_id)}/whep",
                    content=sdp,
                    headers={"Content-Type": "application/sdp"},
                )
            except httpx.HTTPError:
                raise SourceError(503, "Không kết nối được dịch vụ WebRTC.") from None
            if response.status_code != 201:
                camera = await self.status(token)
                if camera.get("auth") == "rejected":
                    raise SourceError(401, camera["message"])
                raise SourceError(
                    502,
                    "Không tạo được phiên WebRTC. Kiểm tra codec và trạng thái camera.",
                )
            location = str(response.url.join(response.headers.get("location", "")))
            parsed = urlsplit(location)
            expected = urlsplit(self.settings.mediamtx_webrtc_url)
            prefix = f"/{self.path(viewer.source_id)}/whep/"
            if (parsed.scheme, parsed.netloc) != (
                expected.scheme,
                expected.netloc,
            ) or not parsed.path.startswith(prefix):
                raise SourceError(502, "MediaMTX trả phiên WebRTC không hợp lệ.")
            viewer.upstream = location
            if self.viewers.get(token) is not viewer:
                await self.close_whep(viewer)
                raise SourceError(410, "Phiên xem đã đóng.")
            return response.text

    async def close_whep(self, viewer: Viewer) -> None:
        """Đóng WHEP qua DELETE, bỏ Location trước await; lỗi mạng không cản cleanup."""
        location, viewer.upstream = viewer.upstream, None
        if location:
            try:
                await self.whep.delete(location)
            except httpx.HTTPError:
                pass

    async def close(self, token: str) -> None:
        """Bỏ lease, đóng WHEP và gỡ path ngay khi viewer cuối cùng dừng."""
        viewer = self.viewers.pop(token, None)
        if viewer is None:
            return
        async with viewer.lock:
            await self.close_whep(viewer)
        async with self.lock:
            if not any(v.source_id == viewer.source_id for v in self.viewers.values()):
                await self.drop_path(viewer.source_id)

    async def drop_path(self, source_id: str) -> None:
        """Gỡ path riêng của ứng dụng để MediaMTX ngắt RTSP; giữ dấu nếu API lỗi."""
        try:
            response = await self.api_request(
                "DELETE", f"/v3/config/paths/delete/{self.path(source_id)}"
            )
            if response.is_success or response.status_code == 404:
                self.paths.discard(source_id)
                self.temporary_urls.pop(source_id, None)
        except SourceError:
            pass

    async def restart(self, source_id: str) -> None:
        """Áp dụng URL vừa sửa cho path đang được xem; MediaMTX quản lý kết nối lại."""
        async with self.lock:
            if source_id in self.paths:
                await self.ensure_path(source_id)

    async def remove(self, source_id: str) -> None:
        """Đóng mọi lease của camera bị xoá, rồi gỡ path MediaMTX nếu còn."""
        tokens = [
            key for key, value in self.viewers.items() if value.source_id == source_id
        ]
        for token in tokens:
            await self.close(token)
        async with self.lock:
            if source_id in self.paths:
                await self.drop_path(source_id)

    async def maintain(self) -> None:
        """Thu hồi lease hết heartbeat và retry dọn path khi Control API phục hồi."""
        while True:
            await asyncio.sleep(5)
            expired = [
                key
                for key, value in self.viewers.items()
                if value.expires < time.monotonic()
            ]
            for token in expired:
                await self.close(token)
            async with self.lock:
                for source_id in tuple(self.paths):
                    if not any(v.source_id == source_id for v in self.viewers.values()):
                        await self.drop_path(source_id)

    async def shutdown(self) -> None:
        """Đóng lease, path và HTTP client; backend không sở hữu tiến trình MediaMTX."""
        self.closed = True
        for token in tuple(self.viewers):
            await self.close(token)
        for source_id in tuple(self.paths):
            await self.drop_path(source_id)
        self.temporary_urls.clear()
        await self.api.aclose()
        await self.whep.aclose()
