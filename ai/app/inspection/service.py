"""Điều phối kiểm tra model trong tiến trình con có timeout."""

import asyncio
import json
import os
import sys
from pathlib import Path

from app.contracts.model import InspectRequest, InspectResult
from app.core.config import Settings


# ----------------------------- Service kiểm tra ------------------------------
class InspectionService:
    """Giới hạn một lượt inspect cùng lúc, kiểm soát đường dẫn và vòng đời worker."""

    def __init__(self, settings: Settings) -> None:
        """Giữ settings và tạo semaphore; không load PyTorch trong tiến trình API."""
        self.settings = settings
        self.root = settings.models_path.resolve()
        self.semaphore = asyncio.Semaphore(1)

    async def inspect(self, request: InspectRequest) -> InspectResult:
        """Đọc model trong root với checksum đã biết và dừng worker khi quá timeout.

        Nhận request từ backend; trả failed nếu đường dẫn/file/định dạng sai.
        Không cho đọc file ngoài root hoặc qua symlink; process bị kết thúc khi
        timeout/cancel, tài nguyên stdout/stderr được thu hồi sau khi thoát.
        """
        relative = Path(request.location)
        path = (self.root / relative).resolve()
        if (
            relative.is_absolute()
            or not path.is_relative_to(self.root)
            or path == self.root
            or path != self.root / relative
        ):
            return InspectResult(
                status="failed", message="Đường dẫn model không hợp lệ."
            )
        if not path.is_file() or path.suffix.lower() not in {".pt", ".onnx"}:
            return InspectResult(
                status="failed", message="File model không tồn tại hoặc sai định dạng."
            )
        if path.stat().st_size > self.settings.max_model_bytes:
            return InspectResult(
                status="failed", message="Model vượt giới hạn kiểm tra."
            )
        async with self.semaphore:
            environment = {
                **os.environ,
                "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            }
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.inspection.worker",
                str(path),
                request.sha256,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=environment,
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(), self.settings.inspect_timeout
                )
                if process.returncode != 0:
                    return InspectResult(
                        status="failed", message="Tiến trình đọc model không hoàn tất."
                    )
                return InspectResult.model_validate(json.loads(stdout))
            except asyncio.TimeoutError:
                return InspectResult(
                    status="failed", message="Đọc metadata quá thời gian chờ."
                )
            except (ValueError, TypeError):
                return InspectResult(
                    status="failed", message="Không đọc được phản hồi metadata."
                )
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
