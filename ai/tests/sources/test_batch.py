"""Kiểm thử thread thực, vòng đời reader và giới hạn tham chiếu frame."""

import gc
import threading
import unittest
import weakref

import numpy as np

from app.media_sources import (
    SourceMeta,
    SourceType,
    StreamBatchReader,
    StreamError,
    SyncBatchReader,
)
from app.media_sources.batch import AutoBatchReader
from app.media_sources.readers.base import BaseReader


# -------------------------- Reader có điều khiển -----------------------------
class ControlledReader(BaseReader):
    """Nguồn giả có event kiểm soát read đang block, hỗ trợ lỗi và reconnect stop."""

    source_type = SourceType.VIDEO

    def __init__(
        self,
        count: int = 1,
        *,
        blocking: bool = False,
        stoppable: bool = True,
        failing: bool = False,
    ) -> None:
        """Tạo fixture, không khởi thread hoặc chiếm capture."""
        super().__init__("fixture")
        self.count = count
        self.blocking = blocking
        self.stoppable = stoppable
        self.failing = failing
        self.is_stream = blocking
        self.waiting = threading.Event()
        self.unblock = threading.Event()
        self.open_calls = 0
        self.close_calls = 0
        self.reference = None

    def open(self) -> "ControlledReader":
        """Mở/reset fixture, đếm lần mở để bắt double-open."""
        if not self._opened:
            self.open_calls += 1
            self._opened = True
            self._frame_index = 0
            self.waiting.clear()
            self.unblock.clear()
        return self

    def read(self) -> tuple[np.ndarray, SourceMeta] | None:
        """Trả số frame đã định rồi block hoặc kết thúc; có thể giả lập lỗi decode."""
        self.ensure_open()
        if self.failing:
            raise RuntimeError("fixture decode failure")
        if self._frame_index < self.count:
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            self.reference = weakref.ref(frame)
            meta = SourceMeta(
                "fixture",
                self.source_type,
                self._frame_index,
                (64, 64),
                is_stream=self.is_stream,
            )
            self._frame_index += 1
            return frame, meta
        if self.blocking:
            self.waiting.set()
            if not self.unblock.wait(5):
                raise RuntimeError("fixture not unblocked")
        return None

    def request_stop(self) -> None:
        """Reader stoppable mô phỏng RTSP đánh thức reconnect ngay khi dừng."""
        if self.stoppable:
            self.unblock.set()

    def close(self) -> None:
        """Đóng idempotent; giữ số lần đóng thật để kiểm tra ownership."""
        if self._opened:
            self.close_calls += 1
        self._opened = False


# --------------------------- Kiểm thử batch file -----------------------------
class SyncBatchTests(unittest.TestCase):
    """File dài không bị cắt theo file ngắn và reader luôn được đóng khi lỗi."""

    def test_unequal_lengths_keep_source_identity_and_exhaustion(self) -> None:
        """Giữ đuôi source dài cùng index gốc, không tự restart khi gọi next sau EOF."""
        short, long = ControlledReader(1), ControlledReader(3)
        batch = SyncBatchReader([short, long])
        with batch:
            identities = [[meta.source_index for meta in metas] for _, metas in batch]
        self.assertEqual(identities, [[0, 1], [1], [1]])
        self.assertEqual(short.close_calls, 1)
        self.assertEqual(long.close_calls, 1)
        self.assertEqual(list(batch), [])
        with batch:
            self.assertEqual(len(list(batch)), 3)
        self.assertEqual(long.open_calls, 2)

    def test_read_failure_closes_every_source(self) -> None:
        """Consumer nhận lỗi nhưng không giữ reader hoặc frame đã đọc trước lỗi."""
        first, broken = ControlledReader(), ControlledReader(failing=True)
        batch = SyncBatchReader([first, broken])
        with self.assertRaises(RuntimeError):
            next(batch)
        self.assertFalse(first.opened)
        self.assertFalse(broken.opened)
        gc.collect()
        self.assertIsNone(first.reference())

    def test_partial_open_failure_cleans_failed_reader(self) -> None:
        """Nếu open reader sau lỗi, cả reader trước và reader lỗi đều được cleanup."""
        first, broken = ControlledReader(), ControlledReader()

        def fail() -> None:
            """Giả lập open tạo tài nguyên rồi mới lỗi."""
            broken._opened = True
            raise RuntimeError("open failure")

        broken.open = fail
        with self.assertRaises(RuntimeError):
            SyncBatchReader([first, broken]).open()
        self.assertEqual(first.close_calls, 1)
        self.assertEqual(broken.close_calls, 1)


# -------------------------- Kiểm thử batch stream ----------------------------
class StreamBatchTests(unittest.TestCase):
    """Thread thật, read có kiểm soát; không cần webcam/mạng hoặc sleep dài."""

    def test_slow_camera_does_not_block_fast_camera(self) -> None:
        """Nguồn chưa có frame không chặn nguồn nhanh; metadata giữ source_index."""
        fast = ControlledReader(1, blocking=True)
        slow = ControlledReader(0, blocking=True)
        batch = StreamBatchReader([fast, slow], wait_timeout=0.2)
        with batch:
            self.assertTrue(slow.waiting.wait(1))
            frames, metas = next(batch)
            self.assertEqual([meta.source_index for meta in metas], [0])
            self.assertEqual(len(frames), 1)
        self.assertEqual(batch._threads, [])
        self.assertEqual(fast.close_calls, 1)
        self.assertEqual(slow.close_calls, 1)

    def test_timed_out_close_keeps_handle_blocks_reopen_and_releases_frames(
        self,
    ) -> None:
        """Không quên thread block; chặn reopen đến khi thread cũ dừng, dọn frame/slot."""
        reader = ControlledReader(1, blocking=True, stoppable=False)
        batch = StreamBatchReader([reader], join_timeout=0.02)
        batch.open()
        self.assertTrue(reader.waiting.wait(1))
        old = list(batch._threads)
        with self.assertRaises(StreamError):
            batch.close()
        self.assertEqual(batch._threads, old)
        self.assertTrue(old[0].is_alive())
        self.assertEqual(batch._slots, [None])
        gc.collect()
        self.assertIsNone(reader.reference())
        with self.assertRaises(StreamError):
            batch.open()
        self.assertEqual(reader.open_calls, 1)
        reader.unblock.set()
        old[0].join(1)
        self.assertFalse(old[0].is_alive())
        batch.close()
        gc.collect()
        self.assertIsNone(reader.reference())
        reader.stoppable = True
        with batch:
            self.assertTrue(reader.waiting.wait(1))
            self.assertEqual(len(next(batch)[0]), 1)
        self.assertEqual(reader.open_calls, 2)
        self.assertEqual(reader.close_calls, 2)

    def test_thread_error_and_no_frame_timeout_close_resources(self) -> None:
        """Lỗi trong thread và nguồn không có frame đều được báo, không treo iterator."""
        for failing in [True, False]:
            reader = ControlledReader(0, blocking=True, failing=failing)
            batch = StreamBatchReader([reader], wait_timeout=0.02)
            with self.assertRaises(StreamError):
                next(batch)
            self.assertEqual(batch._threads, [])
            self.assertFalse(reader.opened)
            self.assertEqual(batch._errors, [None])

    def test_many_cycles_do_not_accumulate_threads_or_frames(self) -> None:
        """50 lần mở/đọc/đóng nhả weakref frame và không tăng thread nền."""
        before = {thread.ident for thread in threading.enumerate()}
        references = []
        reader = ControlledReader(1, blocking=True)
        batch = StreamBatchReader([reader])
        for _ in range(50):
            with batch:
                self.assertTrue(reader.waiting.wait(1))
                frames, _ = next(batch)
                references.append(weakref.ref(frames[0]))
                del frames
            self.assertEqual(batch._threads, [])
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))
        self.assertEqual({thread.ident for thread in threading.enumerate()}, before)
        self.assertEqual(reader.open_calls, 50)
        self.assertEqual(reader.close_calls, 50)

    def test_open_idempotent_and_context_consumer_failure(self) -> None:
        """Mở hai lần không tạo thread thứ hai; consumer lỗi vẫn dọn thread."""
        reader = ControlledReader(1, blocking=True)
        batch = StreamBatchReader([reader])
        with self.assertRaisesRegex(RuntimeError, "consumer"):
            with batch:
                threads = list(batch._threads)
                batch.open()
                self.assertEqual(batch._threads, threads)
                next(batch)
                raise RuntimeError("consumer")
        self.assertEqual(reader.open_calls, 1)
        self.assertFalse(reader.opened)
        self.assertEqual(batch._threads, [])

    def test_completed_stream_does_not_restart(self) -> None:
        """Nguồn finite trong stream trả frame cuối rồi StopIteration ổn định."""
        reader = ControlledReader(1)
        batch = StreamBatchReader([reader])
        self.assertEqual(len(list(batch)), 1)
        self.assertEqual(list(batch), [])
        self.assertFalse(reader.opened)

    def test_live_and_vod_delegate_selection(self) -> None:
        """YouTube sau resolve chọn đúng chiến lược và không trộn VOD với live."""
        for live in [False, True]:
            reader = ControlledReader(1, blocking=live)
            wrapper = AutoBatchReader([reader])
            with wrapper:
                expected = StreamBatchReader if live else SyncBatchReader
                self.assertIsInstance(wrapper._delegate, expected)
                self.assertEqual(len(next(wrapper)[0]), 1)
        live, vod = ControlledReader(1, blocking=True), ControlledReader(1)
        wrapper = AutoBatchReader([live, vod])
        with self.assertRaises(ValueError):
            wrapper.open()
        self.assertFalse(live.opened)
        self.assertFalse(vod.opened)
