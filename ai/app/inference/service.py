"""Chạy worker inference có giới hạn đồng thời, timeout và huỷ khi client ngắt kết nối."""

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

from app.contracts.prediction import PredictRequest
from app.core.config import Settings


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
                stderr=asyncio.subprocess.DEVNULL,
                env={
                    **os.environ,
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                },
            )
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(request.model_dump_json().encode()), 180
                )
                if process.returncode != 0:
                    raise ValueError("Worker inference dừng bất thường.")
                output = json.loads(stdout)
                if output.get("error"):
                    raise ValueError(output["error"])
                return output["result"]
            except asyncio.TimeoutError as error:
                raise ValueError("Inference quá thời gian chờ.") from error
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()

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
        async with self.semaphore:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.inference.video_worker",
                str(model),
                str(source),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=8 * 1024 * 1024,
                env={
                    **os.environ,
                    "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                },
            )
            try:
                process.stdin.write(request.model_dump_json().encode())
                await process.stdin.drain()
                process.stdin.close()
                deadline = asyncio.get_running_loop().time() + 4 * 60 * 60
                completed = False
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise ValueError("Lượt chạy video vượt giới hạn bốn giờ.")
                    line = await asyncio.wait_for(
                        process.stdout.readline(), min(180, remaining)
                    )
                    if not line:
                        break
                    event = json.loads(line)
                    yield event
                    if event.get("type") == "completed":
                        completed = True
                        break
                    if event.get("type") == "error":
                        return
                if not completed:
                    raise ValueError("Luồng kết quả video bị gián đoạn.")
            except asyncio.TimeoutError as error:
                raise ValueError(
                    "AI không trả frame mới trong thời gian chờ."
                ) from error
            finally:
                if process.returncode is None:
                    process.kill()
                await process.wait()
