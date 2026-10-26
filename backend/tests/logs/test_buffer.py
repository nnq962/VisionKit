"""Kiểm tra cursor, giới hạn bộ nhớ, context và lọc nội dung log."""

import logging
import unittest
from concurrent.futures import ThreadPoolExecutor

from app.core.logs import (
    BufferHandler,
    LogBuffer,
    attach_logging,
    detach_logging,
    run_context,
)


# -------------------------- Kiểm thử bộ đệm log ------------------------------
class LogBufferTests(unittest.TestCase):
    """Bảo đảm đọc tăng dần không mất log do bộ lọc và phát hiện mất lịch sử."""

    def test_filtered_pagination_advances_only_scanned_entries(self) -> None:
        """Bản ghi không khớp vẫn tiến cursor; bản ghi chưa xét không bị bỏ qua."""
        buffer = LogBuffer("backend")
        buffer.append("INFO", "không khớp")
        buffer.append("ERROR", "lỗi một", run_id="run-a")
        buffer.append("ERROR", "lỗi hai", run_id="run-a")
        page = buffer.read(limit=1, min_level="ERROR", run_id="run-a")
        self.assertEqual([entry.message for entry in page.items], ["lỗi một"])
        self.assertTrue(page.has_more)
        page = buffer.read(page.next_cursor, min_level="ERROR", run_id="run-a")
        self.assertEqual([entry.message for entry in page.items], ["lỗi hai"])
        page = buffer.read(page.next_cursor)
        self.assertEqual(page.items, [])
        self.assertFalse(page.has_more)

    def test_overflow_and_restart_are_explicit(self) -> None:
        """Ghi đè báo dropped; cursor từ phiên khác báo reset và đọc được log mới."""
        buffer = LogBuffer("backend", capacity=2)
        cursor = buffer.read().next_cursor
        for value in range(4):
            buffer.append("INFO", str(value))
        page = buffer.read(cursor)
        self.assertTrue(page.dropped)
        self.assertEqual([entry.message for entry in page.items], ["2", "3"])
        restarted = LogBuffer("backend")
        restarted.append("INFO", "phiên mới")
        page = restarted.read(page.next_cursor)
        self.assertTrue(page.reset)
        self.assertEqual(page.items[0].message, "phiên mới")

    def test_empty_filter_does_not_replay_old_entries(self) -> None:
        """Lọc không khớp vẫn trả cursor cuối; log khớp đến sau đọc được ngay."""
        buffer = LogBuffer("backend")
        buffer.append("INFO", "khác lượt", run_id="b")
        page = buffer.read(run_id="a")
        self.assertEqual(page.items, [])
        buffer.append("INFO", "đúng lượt", run_id="a")
        self.assertEqual(
            buffer.read(page.next_cursor, run_id="a").items[0].message, "đúng lượt"
        )

    def test_invalid_cursor_and_future_cursor(self) -> None:
        """Cursor sai cú pháp bị từ chối; cursor vượt hiện tại được đặt lại rõ ràng."""
        buffer = LogBuffer("ai")
        with self.assertRaises(ValueError):
            buffer.read("not-a-cursor")
        self.assertTrue(buffer.read(f"{buffer.epoch}:99").reset)

    def test_handler_context_traceback_and_noise_filter(self) -> None:
        """Handler giữ run_id/traceback, bỏ mã màu và không thu access log của logs."""
        buffer = LogBuffer("ai")
        handler = BufferHandler(buffer)
        token = run_context.set("run-a")
        try:
            try:
                raise RuntimeError("lỗi thử")
            except RuntimeError:
                import sys

                record = logging.LogRecord(
                    "app.worker",
                    logging.ERROR,
                    "",
                    1,
                    "\x1b[31mfailed token=normal api_key=hidden",
                    (),
                    sys.exc_info(),
                )
                handler.emit(record)
            handler.emit(
                logging.LogRecord(
                    "uvicorn.access",
                    logging.INFO,
                    "",
                    1,
                    "GET /api/v1/logs?after=x HTTP/1.1 200",
                    (),
                    None,
                )
            )
        finally:
            run_context.reset(token)
        entries = buffer.read().items
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].run_id, "run-a")
        self.assertIn("RuntimeError", entries[0].traceback)
        self.assertNotIn("hidden", entries[0].message)
        self.assertNotIn("\x1b", entries[0].message)

    def test_concurrent_writers_have_unique_ordered_ids(self) -> None:
        """Ghi từ thread pool không trùng id hoặc vượt dung lượng bộ đệm."""
        buffer = LogBuffer("backend", capacity=100)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda value: buffer.append("INFO", str(value)), range(300)))
        page = buffer.read(limit=500)
        self.assertEqual(len(page.items), 100)
        numbers = [int(entry.id.split(":")[1]) for entry in page.items]
        self.assertEqual(numbers, list(range(201, 301)))

    def test_logging_handlers_are_restored(self) -> None:
        """Đóng lifespan không để lại handler hay thay đổi level của logger app."""
        logger = logging.getLogger("app")
        original_handlers, original_level = list(logger.handlers), logger.level
        attached = attach_logging(LogBuffer("backend"))
        detach_logging(attached)
        self.assertEqual(logger.handlers, original_handlers)
        self.assertEqual(logger.level, original_level)
