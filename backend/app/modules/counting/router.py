"""API cấu hình vùng theo nguồn và tạo lượt đếm dùng RunService hiện có."""

import asyncio
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.errors import SourceError
from app.modules.runs.schemas import RunOptions, RunRecord
from app.modules.sources.models import Source

from .schemas import CountingConfig

router = APIRouter(prefix="/counting", tags=["counting"])


# ------------------------- Định danh nội dung nguồn --------------------------
def source_signature(source: Source) -> str:
    """Băm vị trí/checksum/kích thước để phát hiện đổi nguồn mà không trả URL bí mật."""
    values = [
        source.location,
        source.kind.value,
        *[
            source.metadata.get(key)
            for key in ("sha256", "width", "height", "rotation")
        ],
    ]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


# ------------------------------ Nguồn được đếm -------------------------------
def counting_source(request: Request, source_id: str) -> Source:
    """Đọc nguồn đã lưu; chỉ chấp nhận video file hoặc RTSP/RTSPS."""
    source = request.app.state.sources.get(source_id)
    if source.kind.value not in {"video", "stream"}:
        raise SourceError(422, "Đếm theo vùng chỉ hỗ trợ video file và RTSP.")
    return source


# --------------------------- Cấu hình màn giám sát ---------------------------
class MonitorSettings(BaseModel):
    """Lưu model, ngưỡng và giới hạn lượt chạy cho UI; không tự khởi động worker."""

    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=255)
    options: RunOptions = Field(default_factory=RunOptions)
    duration_seconds: int = Field(
        default=3600, ge=60, le=14400, multiple_of=60, strict=True
    )
    continuous: bool = False
    auto_start: bool = False

    @model_validator(mode="after")
    def validate_service_mode(self) -> "MonitorSettings":
        """Tự khởi động chỉ dùng cho chế độ chạy liên tục, tránh ý định mâu thuẫn."""
        if self.auto_start and not self.continuous:
            raise ValueError("Bật Chạy liên tục trước khi bật Tự khởi động.")
        return self


# ----------------------------- Request lưu vùng ------------------------------
class ConfigSave(BaseModel):
    """Nhận cấu hình cùng chữ ký nguồn lúc vẽ, cho phép danh sách rỗng để xoá vùng."""

    model_config = ConfigDict(extra="forbid")
    source_signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    config: CountingConfig
    monitor: MonitorSettings | None = None


# ----------------------------- Request chạy đếm ------------------------------
class CountingRunCreate(ConfigSave):
    """Nhận nguồn/model đã lưu và snapshot vùng; prompt lấy từ cấu hình class của lượt chạy."""

    source_id: UUID
    model_id: str = Field(min_length=1, max_length=255)
    options: RunOptions = Field(default_factory=RunOptions)
    duration_seconds: int = Field(default=3600, ge=1, le=14400, strict=True)


# ---------------------------- Cấu hình đếm có tên ----------------------------
class ProfileSave(ConfigSave):
    """Nhận tên và snapshot độc lập; nhiều cấu hình có thể dùng chung một nguồn."""

    name: str = Field(min_length=1, max_length=100)
    source_id: UUID
    monitor: MonitorSettings

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Bỏ khoảng trắng đầu/cuối; từ chối tên trắng hoặc ký tự điều khiển."""
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Tên cấu hình không được rỗng hoặc chứa ký tự điều khiển.")
        return value


# ---------------------------- Cấu hình đếm có tên ----------------------------
def profile_record(profile_id: str, request: Request) -> dict:
    """Đọc snapshot và lượt riêng; đánh dấu nguồn bị thay đổi/xoá mà không mất cấu hình."""
    database = request.app.state.sources.repository.database
    with database.connection() as connection:
        row = connection.execute(
            "SELECT * FROM counting_profiles WHERE id=? AND deleted_at IS NULL",
            (profile_id,),
        ).fetchone()
    if row is None:
        raise SourceError(404, "Không tìm thấy cấu hình đếm.")
    result = dict(row)
    result.pop("name_key")
    result.pop("deleted_at")
    result["enabled"] = bool(result["enabled"])
    result["runtime"] = json.loads(result.pop("runtime_json"))
    result.update(json.loads(result.pop("snapshot_json")))
    try:
        source = counting_source(request, result["source_id"])
        result["stale"] = source_signature(source) != result["source_signature"]
    except SourceError as error:
        if error.status_code != 404:
            raise
        result["stale"] = True
    if result["stale"]:
        result["current_run_id"] = None
    if result["current_run_id"]:
        try:
            request.app.state.runs.get(result["current_run_id"])
        except SourceError as error:
            if error.status_code not in {404, 410}:
                raise
            result["current_run_id"] = None
    return result


# ---------------------------- Cấu hình đếm có tên ----------------------------
@router.get("/profiles")
def list_profiles(request: Request) -> list[dict]:
    """Liệt kê cấu hình đã lưu theo tên; không mở media hoặc khởi động AI."""
    database = request.app.state.sources.repository.database
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT id FROM counting_profiles WHERE deleted_at IS NULL ORDER BY name_key, id"
        ).fetchall()
    return [profile_record(row["id"], request) for row in rows]


# ---------------------------- Cấu hình đếm có tên ----------------------------
@router.get("/profiles/{profile_id}")
def read_profile(profile_id: UUID, request: Request) -> dict:
    """Trả cấu hình có tên và ID lượt của chính cấu hình đó, không lấy lượt nguồn khác."""
    return profile_record(str(profile_id), request)


# ---------------------------- Cấu hình đếm có tên ----------------------------
def store_profile(
    profile_id: str, body: ProfileSave, request: Request, *, create: bool
) -> dict:
    """Ghi snapshot SQLite nguyên tử, chặn tên trùng và chữ ký nguồn cũ.

    Cập nhật không sửa snapshot hay con trỏ của lượt đang chạy. Nguồn bị xoá trả 404,
    tên trùng/chữ ký cũ trả 409; lỗi rollback toàn bộ giao dịch.
    """
    database = request.app.state.sources.repository.database
    now = datetime.now(timezone.utc).isoformat()
    snapshot = body.model_dump(mode="json", exclude={"name", "source_id"})
    try:
        with database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = counting_source(request, str(body.source_id))
            if source_signature(source) != body.source_signature:
                raise SourceError(
                    409, "Nguồn đã thay đổi. Tải lại nguồn và vẽ lại vùng."
                )
            if not body.config.zones:
                raise SourceError(422, "Vẽ ít nhất một vùng trước khi lưu cấu hình.")
            previous = connection.execute(
                "SELECT * FROM counting_profiles WHERE id=? AND deleted_at IS NULL",
                (profile_id,),
            ).fetchone()
            if not create and previous is None:
                raise SourceError(404, "Không tìm thấy cấu hình đếm.")
            if previous and previous["source_id"] != str(body.source_id):
                current_id = previous["current_run_id"]
                if previous["enabled"] or (
                    current_id and active_run(current_id, request)
                ):
                    raise SourceError(409, "Dừng cấu hình trước khi đổi nguồn.")
            if (
                body.monitor.auto_start
                and connection.execute(
                    "SELECT 1 FROM counting_profiles WHERE source_id=? AND id!=? AND enabled=1 AND deleted_at IS NULL",
                    (str(body.source_id), profile_id),
                ).fetchone()
            ):
                raise SourceError(
                    409, "Nguồn đã có cấu hình chạy liên tục. Dừng cấu hình đó trước."
                )
            values = (
                body.name,
                body.name.casefold(),
                str(body.source_id),
                json.dumps(snapshot, ensure_ascii=False),
            )
            if create:
                connection.execute(
                    "INSERT INTO counting_profiles "
                    "(name,name_key,source_id,snapshot_json,id,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (*values, profile_id, now, now),
                )
            else:
                changed = connection.execute(
                    "UPDATE counting_profiles SET current_run_id=CASE "
                    "WHEN source_id != ? OR json_extract(snapshot_json, '$.source_signature') != ? "
                    "THEN NULL ELSE current_run_id END, name=?,name_key=?,source_id=?,"
                    "snapshot_json=?,updated_at=? WHERE id=?",
                    (
                        str(body.source_id),
                        body.source_signature,
                        *values,
                        now,
                        profile_id,
                    ),
                )
                if changed.rowcount != 1:
                    raise SourceError(404, "Không tìm thấy cấu hình đếm.")
            old_monitor = (
                json.loads(previous["snapshot_json"]).get("monitor", {})
                if previous
                else {}
            )
            if not body.monitor.continuous:
                connection.execute(
                    "UPDATE counting_profiles SET enabled=0 WHERE id=?", (profile_id,)
                )
            elif body.monitor.auto_start and not old_monitor.get("auto_start"):
                connection.execute(
                    "UPDATE counting_profiles SET enabled=1, runtime_json='{}' WHERE id=?",
                    (profile_id,),
                )
    except sqlite3.IntegrityError as error:
        raise SourceError(409, "Tên cấu hình đã tồn tại. Chọn tên khác.") from error
    return profile_record(profile_id, request)


# ---------------------------- Cấu hình đếm có tên ----------------------------
@router.post("/profiles", status_code=201)
def create_profile(body: ProfileSave, request: Request) -> dict:
    """Tạo cấu hình có UUID riêng trong SQLite và trả snapshot đã lưu."""
    return store_profile(str(uuid4()), body, request, create=True)


# ---------------------------- Cấu hình đếm có tên ----------------------------
@router.put("/profiles/{profile_id}")
def update_profile(profile_id: UUID, body: ProfileSave, request: Request) -> dict:
    """Thay bản cấu hình được chọn; các cấu hình cùng video và lượt hiện tại giữ nguyên."""
    return store_profile(str(profile_id), body, request, create=False)


# ---------------------------- Điều phối cấu hình -----------------------------
def creation_lock(request: Request) -> asyncio.Lock:
    """Trả khoá điều phối dùng chung cho chạy, dừng, xoá và supervisor."""
    lock = getattr(request.app.state, "counting_creation_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.counting_creation_lock = lock
    return lock


# ---------------------------- Điều phối cấu hình -----------------------------
def active_run(run_id: str, request: Request) -> bool:
    """Kiểm tra lượt còn active; ID hết hạn hoặc đã dọn được xem là không active."""
    try:
        return request.app.state.runs.get(run_id).status in {"queued", "running"}
    except SourceError as error:
        if error.status_code not in {404, 410}:
            raise
        return False


# ---------------------------- Điều phối cấu hình -----------------------------
async def start_saved_profile(profile_id: UUID, request: Request) -> RunRecord:
    """Tạo lượt theo snapshot đã lưu; caller phải giữ creation_lock để chặn chạy trùng."""
    profile = profile_record(str(profile_id), request)
    if profile["stale"]:
        raise SourceError(
            409, "Nguồn đã thay đổi hoặc bị xoá. Chỉnh lại cấu hình trước khi chạy."
        )
    monitor = profile["monitor"]
    record = await enqueue_counting_run(
        CountingRunCreate(
            source_id=profile["source_id"],
            source_signature=profile["source_signature"],
            config=profile["config"],
            model_id=monitor["model_id"],
            options=monitor["options"],
            duration_seconds=monitor["duration_seconds"],
        ),
        request,
    )
    try:
        database = request.app.state.sources.repository.database
        with database.connection() as connection:
            changed = connection.execute(
                "UPDATE counting_profiles SET current_run_id=? WHERE id=?",
                (record.id, str(profile_id)),
            )
            if changed.rowcount != 1:
                raise SourceError(404, "Không tìm thấy cấu hình đếm.")
    except Exception:
        await request.app.state.runs.cancel(record.id)
        raise
    return record


# ---------------------------- Điều phối cấu hình -----------------------------
@router.post("/profiles/{profile_id}/runs", response_model=RunRecord, status_code=202)
async def start_profile(profile_id: UUID, request: Request) -> RunRecord:
    """Chạy cấu hình và lưu ý định chạy liên tục; thất bại không để ý định mồ côi."""
    async with creation_lock(request):
        selected = profile_record(str(profile_id), request)
        database = request.app.state.sources.repository.database
        with database.connection() as connection:
            occupied = connection.execute(
                "SELECT 1 FROM counting_profiles WHERE source_id=? AND id!=? AND enabled=1 AND deleted_at IS NULL",
                (selected["source_id"], str(profile_id)),
            ).fetchone()
        if occupied:
            raise SourceError(
                409, "Nguồn đã có cấu hình chạy liên tục. Dừng cấu hình đó trước."
            )
        record = await start_saved_profile(profile_id, request)
        profile = profile_record(str(profile_id), request)
        database = request.app.state.sources.repository.database
        with database.connection() as connection:
            connection.execute(
                "UPDATE counting_profiles SET enabled=?,runtime_json='{}' WHERE id=?",
                (int(profile["monitor"].get("continuous", False)), str(profile_id)),
            )
        supervisor = getattr(request.app.state, "counting_supervisor", None)
        if supervisor:
            supervisor.next_attempt.pop(str(profile_id), None)
            supervisor.failures.pop(str(profile_id), None)
        return record


# ---------------------------- Điều phối cấu hình -----------------------------
@router.post("/profiles/{profile_id}/stop")
async def stop_profile(profile_id: UUID, request: Request) -> dict:
    """Tắt ý định chạy trước khi huỷ worker để supervisor không khởi động lại."""
    async with creation_lock(request):
        profile_record(str(profile_id), request)
        database = request.app.state.sources.repository.database
        with database.connection() as connection:
            connection.execute(
                "UPDATE counting_profiles SET enabled=0,runtime_json='{}' WHERE id=?",
                (str(profile_id),),
            )
        # Dùng ID gốc kể cả khi chữ ký nguồn đã đổi và API ẩn kết quả cũ.
        with database.connection() as connection:
            pointer = connection.execute(
                "SELECT current_run_id FROM counting_profiles WHERE id=?",
                (str(profile_id),),
            ).fetchone()
        current_id = pointer["current_run_id"] if pointer else None
        if current_id and active_run(current_id, request):
            await request.app.state.runs.cancel(current_id)
        return profile_record(str(profile_id), request)


# ---------------------------- Điều phối cấu hình -----------------------------
@router.post("/profiles/{profile_id}/duplicate", status_code=201)
async def duplicate_profile(profile_id: UUID, request: Request) -> dict:
    """Nhân bản snapshot với tên riêng; không sao chép worker hoặc bật tự chạy."""
    async with creation_lock(request):
        original = profile_record(str(profile_id), request)
        snapshot = {
            key: original[key] for key in ("source_signature", "config", "monitor")
        }
        snapshot["monitor"] = {**snapshot["monitor"], "auto_start": False}
        database = request.app.state.sources.repository.database
        duplicate_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            index = 1
            while True:
                suffix = " (bản sao)" if index == 1 else f" (bản sao {index})"
                name = original["name"][: 100 - len(suffix)] + suffix
                if not connection.execute(
                    "SELECT 1 FROM counting_profiles WHERE name_key=?",
                    (name.casefold(),),
                ).fetchone():
                    break
                index += 1
            connection.execute(
                "INSERT INTO counting_profiles (id,name,name_key,source_id,snapshot_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                (
                    duplicate_id,
                    name,
                    name.casefold(),
                    original["source_id"],
                    json.dumps(snapshot, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return profile_record(duplicate_id, request)


# ---------------------------- Điều phối cấu hình -----------------------------
@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: UUID, request: Request) -> dict:
    """Đưa cấu hình đã dừng vào thùng rác; giữ snapshot để có thể hoàn tác."""
    async with creation_lock(request):
        profile = profile_record(str(profile_id), request)
        if profile["enabled"] or (
            profile["current_run_id"] and active_run(profile["current_run_id"], request)
        ):
            raise SourceError(409, "Dừng cấu hình trước khi xoá.")
        database = request.app.state.sources.repository.database
        with database.connection() as connection:
            connection.execute(
                "UPDATE counting_profiles SET deleted_at=?,name_key=?,enabled=0 WHERE id=?",
                (
                    datetime.now(timezone.utc).isoformat(),
                    f"deleted:{profile_id}",
                    str(profile_id),
                ),
            )
        return {"id": str(profile_id)}


# ---------------------------- Điều phối cấu hình -----------------------------
@router.post("/profiles/{profile_id}/restore")
async def restore_profile(profile_id: UUID, request: Request) -> dict:
    """Khôi phục cấu hình đã xoá; trả 409 nếu tên đã được dùng lại, không tự chạy AI."""
    database = request.app.state.sources.repository.database
    try:
        with database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT name FROM counting_profiles WHERE id=? AND deleted_at IS NOT NULL",
                (str(profile_id),),
            ).fetchone()
            if row is None:
                raise SourceError(404, "Không tìm thấy cấu hình đã xoá.")
            connection.execute(
                "UPDATE counting_profiles SET deleted_at=NULL,name_key=?,enabled=0 WHERE id=?",
                (row["name"].casefold(), str(profile_id)),
            )
    except sqlite3.IntegrityError as error:
        raise SourceError(
            409,
            "Tên cấu hình đã được dùng lại. Đổi tên cấu hình đang dùng trước khi khôi phục.",
        ) from error
    return profile_record(str(profile_id), request)


# ----------------------------- Đọc cấu hình vùng -----------------------------
@router.get("/sources/{source_id}")
def read_config(source_id: UUID, request: Request) -> dict:
    """Trả vùng đã lưu hoặc null; cấu hình nguồn cũ không được tự áp vào nguồn mới."""
    source = counting_source(request, str(source_id))
    signature = source_signature(source)
    saved = source.metadata.get("zone_counting")
    stale = isinstance(saved, dict) and saved.get("source_signature") != signature
    current_id = None
    pointer = source.metadata.get("zone_counting_run")
    if isinstance(pointer, dict) and pointer.get("source_signature") == signature:
        try:
            current = request.app.state.runs.get(pointer["id"])
            if current.counting is not None:
                current_id = current.id
        except SourceError as error:
            if error.status_code not in {404, 410}:
                raise
    database = request.app.state.sources.repository.database
    with database.connection() as connection:
        owner = connection.execute(
            "SELECT id,enabled FROM counting_profiles WHERE deleted_at IS NULL AND source_id=? "
            "AND (current_run_id=? OR enabled=1) ORDER BY enabled DESC LIMIT 1",
            (str(source_id), current_id),
        ).fetchone()
    return {
        "owner_profile_id": owner["id"] if owner else None,
        "enabled": bool(owner["enabled"]) if owner else False,
        "source_signature": signature,
        "config": saved.get("config")
        if isinstance(saved, dict) and not stale
        else None,
        "monitor": saved.get("monitor")
        if isinstance(saved, dict) and not stale
        else None,
        "current_run_id": current_id,
        "stale": stale,
    }


# ----------------------------- Lưu cấu hình vùng -----------------------------
@router.put("/sources/{source_id}")
def save_config(source_id: UUID, body: ConfigSave, request: Request) -> dict:
    """Ghi vùng vào metadata SQLite của nguồn trong giao dịch, giữ các metadata khác.

    Không mở camera hoặc sửa cấu hình snapshot của run đang chạy. Chữ ký nguồn cũ
    trả 409; source bị xoá đồng thời trả 404. Không tạo migration/schema mới.
    """
    database = request.app.state.sources.repository.database
    with database.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        source = counting_source(request, str(source_id))
        if source_signature(source) != body.source_signature:
            raise SourceError(409, "Nguồn đã thay đổi. Tải lại nguồn và vẽ lại vùng.")
        metadata = dict(source.metadata)
        saved = body.model_dump(mode="json")
        previous = metadata.get("zone_counting")
        if "monitor" not in body.model_fields_set and isinstance(previous, dict):
            saved["monitor"] = previous.get("monitor")
        metadata["zone_counting"] = saved
        connection.execute(
            "UPDATE sources SET metadata_json=? WHERE id=?",
            (json.dumps(metadata, ensure_ascii=False), str(source_id)),
        )
    return read_config(source_id, request)


# ----------------------------- Tạo lượt đếm vùng -----------------------------
@router.post("/runs", response_model=RunRecord, status_code=202)
async def create_counting_run(body: CountingRunCreate, request: Request) -> RunRecord:
    """Snapshot vùng vào run và dùng chung worker/video/relay cùng cơ chế cancel.

    Chỉ chạy YOLOE PT với danh sách prompt đã kiểm tra; dữ liệu vùng không gửi sang AI.
    Vùng chồng nhau đếm độc lập. Video được snapshot như lượt inference thông thường.
    """
    lock = getattr(request.app.state, "counting_creation_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.counting_creation_lock = lock
    async with lock:
        return await enqueue_counting_run(body, request)


# ----------------------- Tạo và gắn lượt đếm vào nguồn -----------------------
async def enqueue_counting_run(body: CountingRunCreate, request: Request) -> RunRecord:
    """Tạo lượt trong khoá, lưu ID theo nguồn để UI khác tìm lại; chặn chạy trùng.

    Snapshot vùng/model không bị sửa khi lưu cấu hình mới. Nếu nguồn bị xoá giữa
    chừng, huỷ worker vừa tạo trước khi trả lỗi và không để lượt chạy mồ côi.
    """
    source = counting_source(request, str(body.source_id))
    if source_signature(source) != body.source_signature:
        raise SourceError(409, "Nguồn đã thay đổi. Tải lại nguồn và vẽ lại vùng.")
    if not body.config.zones:
        raise SourceError(422, "Vẽ ít nhất một vùng trước khi chạy.")
    existing = read_config(body.source_id, request)["current_run_id"]
    if existing and request.app.state.runs.get(existing).status in {
        "queued",
        "running",
    }:
        raise SourceError(
            409, "Nguồn đang chạy đếm. Tải lại màn giám sát để quan sát hoặc dừng."
        )
    options = body.options.model_copy(
        update={"text_prompts": list(body.config.classes), "classes": None}
    )
    runs = request.app.state.runs
    if source.kind.value == "stream":
        record = await runs.create_live(
            body.model_id,
            options,
            str(source.id),
            None,
            body.duration_seconds,
            counting=body.config,
        )
    else:
        source, path = request.app.state.sources.content(str(source.id))
        with path.open("rb") as stream:
            record = await runs.create(
                body.model_id,
                options,
                stream,
                source.metadata.get("original_filename", path.name),
                "video",
                counting=body.config,
            )
    try:
        database = request.app.state.sources.repository.database
        with database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current_source = counting_source(request, str(body.source_id))
            metadata = dict(current_source.metadata)
            metadata["zone_counting_run"] = {
                "id": record.id,
                "source_signature": body.source_signature,
            }
            connection.execute(
                "UPDATE sources SET metadata_json=? WHERE id=?",
                (json.dumps(metadata, ensure_ascii=False), str(body.source_id)),
            )
    except SourceError:
        await runs.cancel(record.id)
        raise
    return record
