"""Điều phối nhiều nguồn; bộ nhớ hữu hạn và không bỏ quên thread khi đóng."""

import threading
import time
from dataclasses import replace
from types import TracebackType

import numpy as np

from .exceptions import StreamError
from .models import SourceMeta
from .readers.base import BaseReader

Batch = tuple[list[np.ndarray], list[SourceMeta]]


# --------------------------- Đọc và quản lý source ---------------------------
class _BaseBatch:
    """Một consumer; file đóng cùng thread, stream cho phép close từ thread khác."""

    def __init__(self, readers: list[BaseReader]) -> None:
        """Giữ 1–16 nguồn; không mở kết nối."""
        if not readers or len(readers) > 16:
            raise ValueError("Batch cần từ 1 đến 16 nguồn.")
        self._readers = readers
        self._opened = False
        self._exhausted = False

    def open(self) -> "_BaseBatch":
        """Mở tất cả; dọn cả reader mở lỗi và mọi reader đã mở trước đó."""
        if self._opened:
            return self
        try:
            for reader in self._readers:
                reader.ensure_open()
        except BaseException:
            self.close()
            raise
        self._opened = True
        self._exhausted = False
        return self

    def close(self) -> None:
        """Đóng hết reader kể cả một close lỗi; báo lỗi đầu tiên sau khi dọn."""
        error = None
        for reader in self._readers:
            try:
                reader.close()
            except Exception as exc:
                error = error or exc
        self._opened = False
        self._exhausted = True
        if error:
            raise StreamError("Không đóng được một reader.") from error

    def ensure_open(self) -> None:
        """Mở lazy; iterator đã kết thúc không tự khởi chạy lại."""
        if self._exhausted:
            raise StopIteration
        if not self._opened:
            self.open()

    def __iter__(self) -> "_BaseBatch":
        """Trả iterator batch."""
        return self

    def __enter__(self) -> "_BaseBatch":
        """Mở tường minh, cho phép sử dụng lại sau khi đã đóng hoàn toàn."""
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Thu hồi mọi reader khi rời context."""
        self.close()

    def release(self) -> None:
        """Alias close để tương thích module gốc."""
        self.close()


# --------------------------- Đọc và quản lý source ---------------------------
class SyncBatchReader(_BaseBatch):
    """Đọc file tuần tự, không dùng executor cho một nguồn; không bỏ đuôi video dài."""

    def __init__(self, readers: list[BaseReader]) -> None:
        """Giữ danh sách nguồn chưa kết thúc; source_index luôn là index gốc."""
        super().__init__(readers)
        self._active: set[int] = set()

    def open(self) -> "SyncBatchReader":
        """Mở các reader và khôi phục tập nguồn khi mở lại tường minh."""
        if not self._opened:
            super().open()
            self._active = set(range(len(self._readers)))
        return self

    def __next__(self) -> Batch:
        """Trả tối đa một frame mỗi nguồn còn sống; hết một nguồn vẫn đọc các nguồn khác."""
        self.ensure_open()
        frames, metas = [], []
        try:
            for index in sorted(self._active):
                result = self._readers[index].read()
                if result is None:
                    self._active.remove(index)
                    self._readers[index].close()
                    continue
                frame, meta = result
                frames.append(frame)
                metas.append(replace(meta, source_index=index))
        except BaseException:
            self.close()
            raise
        if not frames:
            self.close()
            raise StopIteration
        return frames, metas

    def close(self) -> None:
        """Dọn tập nguồn hoạt động và mọi reader."""
        self._active.clear()
        super().close()


# --------------------------- Đọc và quản lý source ---------------------------
class StreamBatchReader(_BaseBatch):
    """Một slot/frame mỗi nguồn; nguồn chậm không chặn frame mới của nguồn khác.

    Thread sở hữu capture và tự close. close quá hạn sẽ raise và vẫn giữ handle,
    cấm open lại đến khi thread cũ kết thúc. Không release capture đang read.
    """

    def __init__(
        self,
        readers: list[BaseReader],
        *,
        join_timeout: float = 2.0,
        wait_timeout: float = 15.0,
    ) -> None:
        """Thiết lập giới hạn chờ thread/frame, tính bằng giây dương."""
        super().__init__(readers)
        if not 0 < join_timeout <= 60 or not 0 < wait_timeout <= 300:
            raise ValueError("Timeout batch không hợp lệ.")
        self._join_timeout = join_timeout
        self._wait_timeout = wait_timeout
        self._condition = threading.Condition()
        self._lifecycle = threading.RLock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._slots: list[tuple[np.ndarray, SourceMeta] | None] = [None] * len(readers)
        self._versions = [0] * len(readers)
        self._seen = [0] * len(readers)
        self._ended = [False] * len(readers)
        self._errors: list[Exception | None] = [None] * len(readers)

    def open(self) -> "StreamBatchReader":
        """Mở nguồn và thread một lần; không tái sử dụng reader còn thread cũ."""
        with self._lifecycle:
            if self._opened and not self._stop.is_set():
                return self
            if any(thread.is_alive() for thread in self._threads):
                raise StreamError("Thread reader cũ chưa dừng; không thể mở lại.")
            self._threads.clear()
            super().open()
            self._stop.clear()
            count = len(self._readers)
            self._slots = [None] * count
            self._versions = [0] * count
            self._seen = [0] * count
            self._ended = [False] * count
            self._errors = [None] * count
            try:
                for index in range(count):
                    thread = threading.Thread(
                        target=self._loop,
                        args=(index,),
                        daemon=True,
                        name=f"media-source-{index}",
                    )
                    thread.start()
                    self._threads.append(thread)
            except BaseException:
                self.close()
                raise
        return self

    def _loop(self, index: int) -> None:
        """Đọc vào slot hữu hạn và tự đóng reader khi lỗi, hết nguồn hoặc có stop."""
        reader = self._readers[index]
        try:
            while not self._stop.is_set():
                result = reader.read()
                if result is None:
                    break
                with self._condition:
                    if self._stop.is_set():
                        break
                    self._slots[index] = result
                    self._versions[index] += 1
                    self._condition.notify_all()
                # Không giữ frame cũ trong biến local khi lần read kế tiếp block.
                result = None
        except Exception as exc:
            with self._condition:
                self._errors[index] = exc
        finally:
            try:
                reader.close()
            except Exception as exc:
                with self._condition:
                    self._errors[index] = exc
            with self._condition:
                self._ended[index] = True
                if self._stop.is_set():
                    self._slots[index] = None
                    self._errors[index] = None
                self._condition.notify_all()

    def __next__(self) -> Batch:
        """Chờ ít nhất một nguồn mới; trả subset với source_index để không tráo camera."""
        self.ensure_open()
        deadline = time.monotonic() + self._wait_timeout
        error = None
        with self._condition:
            while not self._stop.is_set():
                error = next((exc for exc in self._errors if exc is not None), None)
                if error:
                    break
                ready = [
                    index
                    for index, version in enumerate(self._versions)
                    if version > self._seen[index]
                ]
                if ready:
                    frames, metas = [], []
                    for index in ready:
                        frame, meta = self._slots[index]
                        frames.append(frame)
                        metas.append(replace(meta, source_index=index))
                        self._seen[index] = self._versions[index]
                        self._slots[index] = None
                    return frames, metas
                if all(self._ended):
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    error = StreamError("Không nhận được frame trong thời gian chờ.")
                    break
                self._condition.wait(remaining)
        self.close()
        if error:
            raise StreamError("Stream không đọc được frame.") from error
        raise StopIteration

    def close(self) -> None:
        """Dừng trong tổng join_timeout; giữ handle thread còn sống để lần sau thu hồi."""
        with self._lifecycle:
            self._stop.set()
            self._exhausted = True
            self._opened = False
            for reader in self._readers:
                reader.request_stop()
            with self._condition:
                self._slots = [None] * len(self._readers)
                self._errors = [None] * len(self._readers)
                self._condition.notify_all()
            deadline = time.monotonic() + self._join_timeout
            for thread in self._threads:
                thread.join(max(0.0, deadline - time.monotonic()))
            if any(thread.is_alive() for thread in self._threads):
                raise StreamError("Thread đọc source chưa dừng đúng hạn.")
            self._threads.clear()
            super().close()


# --------------------------- Đọc và quản lý source ---------------------------
class AutoBatchReader(_BaseBatch):
    """Chọn chiến lược sau khi resolve YouTube, phân biệt video thường với live."""

    def __init__(self, readers: list[BaseReader]) -> None:
        """Chưa mở nguồn và chưa tạo delegate."""
        super().__init__(readers)
        self._delegate: SyncBatchReader | StreamBatchReader | None = None

    def open(self) -> "AutoBatchReader":
        """Mở metadata trước, rồi chuyển quyền sở hữu cho batch tương ứng."""
        if self._opened:
            return self
        if self._delegate is not None:
            self.close()
        try:
            super().open()
            modes = {reader.is_stream for reader in self._readers}
            if len(modes) != 1:
                raise ValueError(
                    "Không trộn YouTube live và video thường trong cùng batch."
                )
            cls = StreamBatchReader if True in modes else SyncBatchReader
            self._delegate = cls(self._readers)
            self._delegate.open()
        except BaseException:
            self.close()
            raise
        return self

    def __next__(self) -> Batch:
        """Đọc từ delegate; đóng trạng thái wrapper khi delegate hết nguồn/lỗi."""
        self.ensure_open()
        try:
            return next(self._delegate)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Đóng delegate trước; nếu thread chưa dừng phải giữ nguyên delegate."""
        self._opened = False
        self._exhausted = True
        if self._delegate is not None:
            self._delegate.close()
            self._delegate = None
        super().close()
