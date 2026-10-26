"""Điều phối kiểm tra model trong tiến trình con có timeout."""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from app.contracts.model import InspectRequest, InspectResult
from app.core.config import Settings
from app.core.worker_logs import drain_stderr, read_worker_output, stop_worker

logger = logging.getLogger(__name__)


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
                stderr=asyncio.subprocess.PIPE,
                env=environment,
            )
            stderr_task = asyncio.create_task(drain_stderr(process.stderr))
            logger.info("Worker đọc metadata đã khởi động; pid=%s.", process.pid)
            try:
                stdout, _ = await asyncio.wait_for(
                    read_worker_output(process), self.settings.inspect_timeout
                )
                if process.returncode != 0:
                    logger.error(
                        "Worker đọc metadata dừng bất thường; mã=%s.",
                        process.returncode,
                    )
                    return InspectResult(
                        status="failed", message="Tiến trình đọc model không hoàn tất."
                    )
                output = json.loads(stdout)
                result = InspectResult.model_validate(output)
                if result.status == "failed":
                    logger.error(
                        "Đọc metadata thất bại: %s",
                        result.message,
                        extra={"worker_traceback": output.get("traceback")},
                    )
                else:
                    logger.info("Đọc metadata hoàn tất: %s.", result.status)
                return result
            except asyncio.TimeoutError:
                logger.error("Đọc metadata quá thời gian chờ.")
                return InspectResult(
                    status="failed", message="Đọc metadata quá thời gian chờ."
                )
            except (ValueError, TypeError):
                logger.exception("Không đọc được phản hồi metadata.")
                return InspectResult(
                    status="failed", message="Không đọc được phản hồi metadata."
                )
            finally:
                await stop_worker(process, stderr_task)
                logger.info("Worker đọc metadata đã dừng; mã=%s.", process.returncode)
