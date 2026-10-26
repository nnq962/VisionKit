"""Chạy worker inference có giới hạn đồng thời, timeout và huỷ khi client ngắt kết nối."""

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path

from app.contracts.prediction import PredictRequest, StreamPredictRequest
from app.core.config import Settings
from app.core.worker_logs import drain_stderr, read_worker_output, stop_worker

logger = logging.getLogger(__name__)


# ----------------------------- Service inference -----------------------------
class InferenceService:
    """Chỉ chạy một worker inference cùng lúc; file nằm trong storage được cấu hình."""

    def __init__(self, settings: Settings) -> None:
        """Giữ settings và semaphore; không load model khi API khởi động."""
        self.settings = settings
        self.semaphore = asyncio.Semaphore(1)

    def path(self, root: Path, location: str) -> Path:
        """Trả file trong root, từ chối đường dẫn tuyệt đối/symlink/escape hoặc file mất."""
        relative = Path(location)
        root = root.resolve()
        path = (root / relative).resolve()
        if (
            relative.is_absolute()
            or not path.is_relative_to(root)
            or path != root / relative
            or not path.is_file()
        ):
            raise ValueError("File inference không hợp lệ hoặc không còn tồn tại.")
        return path

    async def predict(self, request: PredictRequest) -> dict:
        """Xác minh đường dẫn rồi chạy subprocess tối đa 180 giây, luôn kill khi huỷ/timeout."""
        model = self.path(self.settings.models_path, request.model_location)
        source = self.path(
            self.settings.runs_path or self.settings.models_path.parent / "runs",
            request.source_location,
        )
        if (
            model.suffix not in {".pt", ".onnx"}
            or model.stat().st_size > self.settings.max_model_bytes
            or source.stat().st_size > 20 * 1024 * 1024
        ):
            raise ValueError("File inference vượt giới hạn hoặc sai định dạng.")
        async with self.semaphore:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.inference.worker",
                str(model),
                str(source),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                },
            )
            stderr_task = asyncio.create_task(drain_stderr(process.stderr))
            logger.info("Worker inference đã khởi động; pid=%s.", process.pid)
            try:
                stdout, _ = await asyncio.wait_for(
                    read_worker_output(process, request.model_dump_json().encode()), 180
                )
                if process.returncode != 0:
                    logger.error(
                        "Worker inference dừng bất thường; mã=%s.", process.returncode
                    )
                    raise ValueError("Worker inference dừng bất thường.")
                output = json.loads(stdout)
                if output.get("error"):
                    logger.error(
                        "Inference ảnh thất bại: %s",
                        output["error"],
                        extra={"worker_traceback": output.get("traceback")},
                    )
                    raise ValueError(output["error"])
                return output["result"]
            except asyncio.TimeoutError as error:
                logger.error("Inference quá thời gian chờ.")
                raise ValueError("Inference quá thời gian chờ.") from error
            finally:
                await stop_worker(process, stderr_task)
                logger.info("Worker inference đã dừng; mã=%s.", process.returncode)

    async def video(self, request: PredictRequest) -> AsyncIterator[dict]:
        """Phát NDJSON frame từ worker, giới hạn idle 180 giây và tổng lượt chạy bốn giờ.

        Generator bị huỷ/ngắt kết nối sẽ kill worker và giải phóng semaphore;
        không gom toàn bộ frame trong bộ nhớ. Tối đa 8 MiB cho một event.
        """
        model = self.path(self.settings.models_path, request.model_location)
        source = self.path(
            self.settings.runs_path or self.settings.models_path.parent / "runs",
            request.source_location,
        )
        if (
            model.suffix not in {".pt", ".onnx"}
            or model.stat().st_size > self.settings.max_model_bytes
            or source.suffix not in {".mp4", ".mov", ".webm", ".ogv"}
            or source.stat().st_size > self.settings.max_video_bytes
        ):
            raise ValueError("Video/model vượt giới hạn hoặc sai định dạng.")
        async with aclosing(self._stream_worker(request, model, source)) as events:
            async for event in events:
                yield event

    async def stream(self, request: StreamPredictRequest) -> AsyncIterator[dict]:
        """Xác minh model local và chạy RTSP worker riêng, không mở nguồn mạng trong API process."""
        model = self.path(self.settings.models_path, request.model_location)
        if (
            model.suffix not in {".pt", ".onnx"}
            or model.stat().st_size > self.settings.max_model_bytes
        ):
            raise ValueError("Model stream vượt giới hạn hoặc sai định dạng.")
        async with aclosing(self._stream_worker(request, model)) as events:
            async for event in events:
                yield event

    async def _stream_worker(
        self,
        request: PredictRequest | StreamPredictRequest,
        model: Path,
        source: Path | None = None,
    ) -> AsyncIterator[dict]:
        """Dùng chung vòng NDJSON bounded và kill/reap khi huỷ, lỗi, timeout hoặc EOF.

        RTSP chạy module riêng, URL chỉ qua stdin; video vẫn giữ protocol file/pipe.
        """
        live = isinstance(request, StreamPredictRequest)
        label = "RTSP" if live else "video"
        module = "app.inference.stream_worker" if live else "app.inference.video_worker"
        arguments = [str(model)] if live else [str(model), str(source)]
        async with self.semaphore:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                module,
                *arguments,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=8 * 1024 * 1024,
                env={
                    **os.environ,
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                },
            )
            stderr_task = asyncio.create_task(drain_stderr(process.stderr))
            logger.info("Worker %s đã khởi động; pid=%s.", label, process.pid)
            try:
                payload = (
                    request.worker_payload()
                    if live
                    else request.model_dump_json().encode()
                )
                process.stdin.write(payload)
                await process.stdin.drain()
                process.stdin.close()
                maximum = request.duration_seconds + 180 if live else 4 * 60 * 60
                deadline = asyncio.get_running_loop().time() + maximum
                completed = False
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise ValueError("Lượt chạy vượt thời gian cho phép.")
                    line = await asyncio.wait_for(
                        process.stdout.readline(), min(180, remaining)
                    )
                    if not line:
                        break
                    event = json.loads(line)
                    if event.get("type") == "error":
                        if live:
                            event = {
                                "type": "error",
                                "error": "Không xử lý được RTSP. Kiểm tra model, camera và kết nối.",
                            }
                        logger.error(
                            "Inference %s thất bại: %s",
                            label,
                            event.get("error"),
                            extra={"worker_traceback": event.pop("traceback", None)},
                        )
                    yield event
                    if event.get("type") == "completed":
                        completed = True
                        break
                    if event.get("type") == "error":
                        return
                if not completed:
                    raise ValueError("Luồng kết quả bị gián đoạn.")
            except asyncio.TimeoutError as error:
                raise ValueError(
                    "AI không trả frame mới trong thời gian chờ."
                ) from error
            finally:
                await stop_worker(process, stderr_task)
                logger.info("Worker %s đã dừng; mã=%s.", label, process.returncode)
