"""Đọc stderr worker liên tục mà không trộn vào stdout JSON hoặc chờ trình duyệt."""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)
MAX_WORKER_OUTPUT_BYTES = 8 * 1024 * 1024


# ----------------------------- Thu stderr worker -----------------------------
async def drain_stderr(reader: asyncio.StreamReader) -> None:
    """Đọc chunk hữu hạn, ghép dòng tối đa 4096 byte và giới hạn 20 bản ghi mỗi giây.

    Vẫn rút pipe khi quá giới hạn để worker không bị chặn. Dòng quá dài bị cắt,
    log bỏ bớt được báo tổng hợp. Context run_id kế thừa từ task cha.
    """
    pending = b""
    window = time.monotonic()
    emitted = 0
    skipped = 0
    while True:
        chunk = await reader.read(4096)
        if not chunk:
            if pending:
                if emitted < 20:
                    logger.info("%s", pending.decode("utf-8", errors="replace"))
                else:
                    skipped += 1
            if skipped:
                logger.warning("Đã lược bớt %s dòng stderr worker.", skipped)
            return
        pending += chunk
        while b"\n" in pending or b"\r" in pending or len(pending) >= 4096:
            split = min(
                (
                    index
                    for index in (pending.find(b"\n"), pending.find(b"\r"))
                    if index >= 0
                ),
                default=4096,
            )
            split = min(split, 4096)
            line, pending = pending[:split], pending[split + (split < 4096) :]
            if time.monotonic() - window >= 1:
                if skipped:
                    logger.warning("Đã lược bớt %s dòng stderr worker.", skipped)
                window, emitted, skipped = time.monotonic(), 0, 0
            if not line.strip():
                continue
            if emitted < 20:
                logger.info("%s", line.decode("utf-8", errors="replace"))
                emitted += 1
            else:
                skipped += 1


# ---------------------------- Đọc stdout độc lập -----------------------------
async def read_worker_output(
    process: asyncio.subprocess.Process, payload: bytes | None = None
) -> tuple[bytes, None]:
    """Gửi stdin nếu có, đọc stdout và đợi worker; stderr do drain_stderr đọc riêng.

    Trả tuple tương thích communicate; giới hạn stdout ở 8 MiB và ném ValueError
    khi vượt giới hạn. Bên gọi phải chạy stop_worker trong finally để dọn pipe.
    Stderr do drain_stderr đọc riêng; không trộn log vào JSON kết quả.
    """
    if payload is not None and process.stdin:
        try:
            process.stdin.write(payload)
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            # Worker có thể trả lỗi rồi thoát trước khi đọc stdin.
            pass
        finally:
            process.stdin.close()
    output = bytearray()
    while chunk := await process.stdout.read(65536):
        if len(output) + len(chunk) > MAX_WORKER_OUTPUT_BYTES:
            logger.error("Phản hồi worker vượt giới hạn 8 MiB.")
            raise ValueError("Phản hồi worker vượt giới hạn 8 MiB.")
        output.extend(chunk)
    await process.wait()
    return bytes(output), None


# --------------------------- Dừng và thu hồi worker --------------------------
async def stop_worker(
    process: asyncio.subprocess.Process, stderr_task: asyncio.Task
) -> None:
    """Kill worker còn chạy, rút stdout còn lại và đợi task stderr kết thúc.

    Rút pipe theo chunk hữu hạn kể cả sau timeout/hủy/overflow để process.wait
    không treo khi transport stdout đang tạm ngừng vì đầy buffer.
    """
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    try:
        while await process.stdout.read(65536):
            pass
        await process.wait()
    finally:
        await asyncio.gather(stderr_task, return_exceptions=True)
