"""Giữ ý định chạy cấu hình qua restart, nối lượt và phục hồi khi mất dữ liệu AI."""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import FastAPI, Request

from app.core.errors import SourceError

from .router import active_run, creation_lock, profile_record, start_saved_profile

logger = logging.getLogger(__name__)


# ----------------------- Giám sát cấu hình chạy liên tục ---------------------
class CountingSupervisor:
    """Điều phối lượt có hạn thành dịch vụ liên tục, thử lại có backoff và watchdog.

    Thuộc tính:
        app: App sở hữu DB và RunService; một supervisor trong mỗi backend.
        next_attempt: Mốc monotonic thử lại, không dùng thời gian tường để điều phối.
    """

    def __init__(self, app: FastAPI) -> None:
        """Giữ app và bộ đếm thử lại; chưa tạo worker hay truy cập camera."""
        self.app = app
        self.request = Request({"type": "http", "app": app})
        self.database = app.state.sources.repository.database
        self.next_attempt: dict[str, float] = {}
        self.failures: dict[str, int] = {}
        self.clock = time.monotonic
        self.watchdog_seconds = 45
        self.paused = False

    def startup(self) -> None:
        """Chỉ khôi phục cấu hình đang bật có auto_start; tôn trọng lần Dừng trước đó."""
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE counting_profiles SET enabled=0,runtime_json='{}' "
                "WHERE deleted_at IS NULL AND COALESCE(json_extract(snapshot_json, '$.monitor.auto_start'),0)=0"
            )

    def runtime(
        self, profile_id: str, phase: str, error: str | None = None, delay: float = 0
    ) -> None:
        """Ghi trạng thái nhỏ vào SQLite để UI khác quan sát; không ghi URL camera."""
        retry_at = (
            (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            if delay
            else None
        )
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE counting_profiles SET runtime_json=? WHERE id=? AND deleted_at IS NULL",
                (
                    json.dumps({"phase": phase, "error": error, "retry_at": retry_at}),
                    profile_id,
                ),
            )

    def retry(self, profile_id: str, error: str) -> None:
        """Lùi lần thử từ 2 đến 60 giây khi lỗi liên tiếp, tránh vòng tạo worker vô hạn."""
        failures = min(self.failures.get(profile_id, 0) + 1, 6)
        self.failures[profile_id] = failures
        delay = min(60, 2**failures)
        self.next_attempt[profile_id] = self.clock() + delay
        self.runtime(profile_id, "retrying", error, delay)

    async def tick(self) -> None:
        """Kiểm tra từng cấu hình bật; nối lượt, phát hiện worker im lặng và thử lại.

        Cùng creation_lock với các API nên Dừng/xoá không đua với lần tạo mới.
        Lỗi cấu hình/nguồn đánh blocked; lỗi hạ tầng thử lại có giới hạn tần suất.
        """
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id,current_run_id FROM counting_profiles WHERE enabled=1 AND deleted_at IS NULL ORDER BY created_at,id"
            ).fetchall()
        for row in rows:
            profile_id = row["id"]
            async with creation_lock(self.request):
                try:
                    profile = profile_record(profile_id, self.request)
                    if not profile["enabled"]:
                        continue
                    if profile["stale"] or not profile["monitor"].get("continuous"):
                        if row["current_run_id"] and active_run(
                            row["current_run_id"], self.request
                        ):
                            await self.app.state.runs.cancel(row["current_run_id"])
                        self.runtime(
                            profile_id,
                            "blocked",
                            "Nguồn đã thay đổi. Kiểm tra và lưu lại cấu hình.",
                        )
                        continue
                    run = (
                        self.app.state.runs.get(profile["current_run_id"])
                        if profile["current_run_id"]
                        else None
                    )
                    if run and run.status in {"queued", "running"}:
                        age = (
                            datetime.now(timezone.utc)
                            - datetime.fromisoformat(run.updated_at)
                        ).total_seconds()
                        if run.status == "running" and age > self.watchdog_seconds:
                            await self.app.state.runs.cancel(run.id)
                            self.retry(
                                profile_id, "AI không gửi dữ liệu. Đang kết nối lại."
                            )
                        else:
                            if run.result:
                                self.failures.pop(profile_id, None)
                            self.runtime(profile_id, "running")
                        continue
                    if self.clock() < self.next_attempt.get(profile_id, 0):
                        continue
                    if (
                        run
                        and run.status in {"failed", "cancelled"}
                        and profile["runtime"].get("phase") != "retrying"
                    ):
                        self.retry(profile_id, "Lượt AI bị gián đoạn. Đang thử lại.")
                        continue
                    await asyncio.wait_for(
                        start_saved_profile(UUID(profile_id), self.request), timeout=15
                    )
                    self.next_attempt.pop(profile_id, None)
                    self.runtime(profile_id, "running")
                    # Snapshot cũ của các lượt tự nối không cần giữ 24 giờ, tránh đầy ổ đĩa.
                    if run:
                        await self.app.state.runs.finish(run.id)
                except SourceError as error:
                    if error.status_code in {400, 404, 410, 422}:
                        self.runtime(
                            profile_id,
                            "blocked",
                            "Nguồn hoặc model không khả dụng. Kiểm tra cấu hình.",
                        )
                    else:
                        self.retry(profile_id, "Chưa thể chạy AI. Đang thử lại.")
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("Chưa thể phục hồi cấu hình đếm %s.", profile_id)
                    self.retry(profile_id, "Chưa thể kết nối AI. Đang thử lại.")

    async def run(self) -> None:
        """Chạy vòng nền mỗi giây đến khi lifespan huỷ; không dừng vì lỗi một cấu hình."""
        self.startup()
        while True:
            try:
                if not self.paused:
                    await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Supervisor đếm tạm thời không đọc được trạng thái.")
            await asyncio.sleep(1)
