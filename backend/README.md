# VisionKit Backend

FastAPI + SQLite + local file storage, managed by uv with Python 3.10. This module manages data and APIs; AI/inference belongs to a separate module.

## Development

From `backend/`:

```bash
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API documentation: http://localhost:8000/docs
- Health: `GET /api/v1/health`
- `.python-version` selects Python 3.10; commit `uv.lock`, exclude `.venv/`.
- Startup initializes SQLite and applies migrations without deleting existing data.

Defaults point to `data/` at the monorepo root, independently of the current working directory. To override, copy `.env.example` to `.env`, adjust paths/origins, then run:

```bash
uv run --env-file .env uvicorn app.main:app --reload --port 8000
```

Relative paths in environment variables are resolved from the process working directory. The example values assume commands run inside `backend/`.

## Structure

```text
app/
  main.py                       # Application factory and lifespan
  api/                          # Versioned router and dependencies
  core/                         # Settings and shared errors
  db/                           # SQLite connections and schema migrations
  storage/local.py              # Managed image file storage
  modules/sources/
    router.py                   # HTTP endpoints
    schemas.py                  # Request/response contracts
    models.py                   # Source record and kind
    repository.py               # SQLite CRUD
    service.py                  # File + metadata orchestration
```

The previous `backend/db/` implementation has moved into `app/db/` and `app/modules/sources/`; the database location and schema remain compatible. Add new schema migrations without editing already applied entries.

## Source APIs

| Method | Path | Behaviour |
|---|---|---|
| POST | `/api/v1/sources/inspect` | Transient JPEG preview and X-Image-Width/Height/Format headers; no library record |
| POST | `/api/v1/sources/upload` | Multipart `file`, optional `name`, `kind=image\|screen\|video` |
| GET | `/api/v1/sources` | Page `{items,total,limit,offset}`; optional `kind`, `q` (name substring, Unicode case-insensitive), `limit` (1–1000), `offset` |
| GET | `/api/v1/sources/{id}` | Source details, metadata, relative `content_url` |
| GET | `/api/v1/sources/{id}/content` | Original image/video with verified MIME; HTTP Range supported |
| GET | `/api/v1/sources/{id}/preview` | Video thumbnail, HEIC JPEG preview, or original image |
| PATCH | `/api/v1/sources/{id}` | Rename via JSON `{ "name": "New name" }` |
| DELETE | `/api/v1/sources/{id}` | Delete record and its original/preview files; status 204 |

Images are checked by decoded content, not by their filename or declared MIME. Supported image formats: JPEG, PNG, WebP, GIF, BMP, AVIF, HEIC/HEIF, subject to Pillow codec support. Default limits: 20 MiB/file and 64 million pixels. Metadata includes displayed width/height (respecting EXIF orientation), file size, actual format/MIME and original filename. File names on disk are generated UUIDs. These upload APIs handle local media files. RTSP configuration, preview and inference use the separate endpoints documented below.

Data lives in:

```text
data/
  visionkit.sqlite3
  sources/<generated-name>.<actual-format>
```

Deleting a source does not delete files outside the managed source directory. Failed DB inserts remove the new file; failed DB deletes restore the staged file. Filesystem and SQLite are not a single atomic transaction: abrupt process/power failure between operations can leave an orphan file; cleanup/reconciliation can be added separately.

SQLite uses WAL on local storage. Paths can be changed with `VISIONKIT_DB_PATH` and `VISIONKIT_SOURCES_PATH`. No model is loaded and no camera connection is opened.

## Checks

```bash
uv run python -m unittest discover -s tests -v
uv run ruff check app tests
uv run ruff format --check app tests
```

Tests use temporary databases and source folders; they do not alter the real source library.

## iPhone photos

HEIC/HEIF decoding uses `pillow-heif` (libheif), while JPEG/PNG and other formats use Pillow. Original uploaded bytes are retained. HEIC sources additionally store a `.preview.jpg` sidecar, at most 2048px on its longest edge, with rotation applied and colour profile retained when available. Source metadata describes the full-resolution original, not the downscaled preview. `content_url` returns original bytes and MIME; `preview_url` is the browser-compatible version. Deleting a source, or rolling back an insert, handles both files.

The web uses `/sources/inspect` to view HEIC before saving: it temporarily sends the original image to the backend, receives a JPEG and metadata, then discards the temporary file. This does not create a library entry. The backend supports up to 64 million pixels (including 48 MP iPhone images) and 20 MiB/file. This feature covers JPEG and HEIC/HEIF photos; Apple ProRAW/DNG and Live Photo video are outside this scope.

## Video uploads

Install system FFmpeg (includes ffprobe): `brew install ffmpeg` on macOS, or `sudo apt install ffmpeg` on Debian/Ubuntu devices. No AI dependency is needed. The server reads metadata using [ffprobe](https://ffmpeg.org/ffprobe.html) and decodes one frame with FFmpeg, each with a 30-second timeout and local protocols only.

POST `/api/v1/sources/upload` with `kind=video`, `file`, and optional `name`. MP4/MOV, WebM and OGV are accepted after content inspection. The original is retained; metadata includes width/height, duration, FPS when available, codec, size and MIME. A JPEG thumbnail is stored alongside it. `content_url` returns the video and supports HTTP Range (206) for seeking; `preview_url` returns the JPEG thumbnail. List, rename and delete use the existing source endpoints. Delete and rollback handle both files.

Default video limit is 200 MiB, configurable with `VISIONKIT_MAX_VIDEO_UPLOAD_MB`. Images retain their 20 MiB limit. The web proxy limit is 210 MiB, so increase it too if raising the backend limit. The Next proxy can buffer large requests; use a streaming reverse proxy for larger deployments or memory-constrained boards. These limits apply after multipart parsing; a production reverse proxy should also cap request body size.

Videos are not transcoded. Browser playback depends on codec support; MP4/H.264 is a practical choice. Invalid or undecodable videos return 415, oversized uploads 413, missing FFmpeg 503. Validation checks metadata and the first frame, not every frame in the file.

## Model catalog and downloads

The Model Hub uses a curated catalog of 83 `.pt` weights across YOLO26, YOLO11, YOLOv8, YOLOE-26 and YOLOE-11. The checked-in manifest at `app/modules/models/catalog/ultralytics.json` pins official `ultralytics/assets` release `v8.4.0`, URLs, byte sizes and GitHub SHA-256 digests. Update the manifest deliberately when adopting a new release; the backend does not import Ultralytics or PyTorch. Downloading verifies the file's bytes and checksum, not runtime compatibility with the AI module.

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/v1/models/catalog` | Families and downloadable variants, sizes and checksums |
| POST | `/api/v1/models/downloads` | JSON `{ "catalog_id": "yolo11n.pt" }`; returns 202 with a background job |
| GET | `/api/v1/models/downloads` | Active jobs and latest 50 jobs |
| GET | `/api/v1/models/downloads/{id}` | Status, downloaded/total bytes, progress and error |
| DELETE | `/api/v1/models/downloads/{id}` | Cancel active job and clean partial file |
| GET | `/api/v1/models` | Models successfully saved in SQLite |
| GET | `/api/v1/models/{id}` | Model metadata and relative file location |
| DELETE | `/api/v1/models/{id}` | Delete weights and metadata; restore weights if DB delete fails |

Model files default to `data/models/`, configurable via `VISIONKIT_MODELS_PATH`. SQLite schema migration 2 adds `models` and `model_downloads`, preserving existing sources. Workers stream into `<job-id>.part`, verify exact length and SHA-256, rename to `.pt`, then commit the model record and completed job in one DB transaction. Failed inserts remove the new file; file/DB operations are not power-failure atomic, so a crash between rename and commit can leave an orphan `.pt`. No arbitrary download URL or storage path is accepted from the client.

Run **one Uvicorn worker** for this MVP download manager. It supports two concurrent downloads and up to ten active/queued jobs, a 1 GiB/model cap, 30-second network read timeout and 15-minute transfer timeout. The configured proxy may need its own timeout adjustment outside local development. Downloads continue when the browser navigates away or disconnects. The web polls actual byte progress every 700 ms while active, and refreshes the library/history every four seconds while idle. Startup marks unfinished jobs failed and removes `.part` files; the user can retry from scratch. This is not an automatic resume or a distributed job queue.

The previous browser-only Model Hub preview data is ignored. The real library always comes from SQLite. Model export and loading the weights for inference remain separate features.

## Upload custom models and pipeline selection

POST `/api/v1/models/upload` accepts multipart `file` (`.pt` or `.onnx`) and optional `name` (1–120 characters). Legacy optional `family`/`task` fields remain accepted. The backend streams the upload, computes SHA-256, saves a UUID file and SQLite record, then queues AI metadata inspection. HTTP 201 returns the stored model and its `inspection` status; inspection continues after the response. Catalog downloads also queue inspection after successful storage.

Upload defaults to **200 MiB**, configurable with `VISIONKIT_MAX_MODEL_UPLOAD_MB`. GET `/api/v1/models/catalog` exposes `max_upload_bytes`. The web proxy allows 210 MiB. Invalid extension returns 415, empty/invalid form 422, oversized file 413. Failed DB inserts remove the new file; duplicate filenames never overwrite existing weights.

Start the AI service as documented in `../ai/README.md`. `VISIONKIT_AI_URL` defaults to `http://127.0.0.1:8001`; both services must share `VISIONKIT_MODELS_PATH`. Backend has no Torch/Ultralytics dependency. Migration 3 adds persistent `inspection_json` without replacing existing models. Existing models start as `uninspected` and can be inspected when selected.

| Method | Path | Behaviour |
|---|---|---|
| POST | `/api/v1/models/{id}/inspect` | Queue/retry metadata extraction; returns 202 with model |
| GET | `/api/v1/models/{id}` | Current stored model, inferred family/task and inspection result |
| PATCH | `/api/v1/models/{id}/metadata` | Manual fallback JSON `{ "family": "yolo", "task": "detect" }` |

Inspection states: `uninspected`, `queued`, `processing`, `ready`, `needs_input`, `failed`, `unavailable`, `manual`. Results include format, family, task, names/class count, image size, input shape, stride, architecture, scale, parameters and version where available. AI downtime preserves the upload and returns `unavailable`; users can retry. Missing ONNX metadata permits manual fallback; corrupt/rejected files cannot be manually approved. A ready result describes extracted metadata, not inference validation. Startup/shutdown marks interrupted inspections unavailable for explicit retry.

The web polls selected pending models, shows inferred metadata and permits the next pipeline step only after `ready` or `manual`, checking the file still exists with the recorded size. This is not a full checksum rescan or inference test. Selection and unsaved upload File/name persist in browser IndexedDB; new files upload automatically for temporary inspection; **Lưu vào thư viện** promotes the uploaded file. Active uploads warn before reload and do not resume after reload. Model Hub and the picker share the same backend library.

## Temporary model preview and selection

The pipeline picker now uses `POST /api/v1/models/temporary` (multipart `file`, optional `name`). Selecting a file uploads it immediately and queues metadata extraction. The response contains a model ID usable with the existing detail/inspect/configuration APIs and later pipeline execution. Temporary models have `expires_at`, remain outside `GET /models` / Model Hub, and can pass the selection step after metadata is ready or manually configured. Running inference remains a separate, unimplemented step.

`POST /api/v1/models/{id}/save` with `{ "name": "Model name" }` promotes the same file/ID/metadata into the library, clearing expiry; no second upload or file copy. This endpoint is idempotent for library membership. The original `/upload` endpoint retains its persistent-upload semantics for API compatibility.

Migration 4 adds nullable `expires_at`. Temporary bookkeeping lives in SQLite for restart/reload recovery, while library queries only return records without expiry. Files share managed model storage so the AI service can inspect both. Temporary records expire after **24 hours of inactivity**; access through the detail endpoint, retry/configuration or promotion renews the lease. Startup and a ten-minute background sweep remove expired records/files and cancel their inspection tasks. Expired IDs return 410 until cleanup, then 404. Explicit discard/replacement deletes temporary files immediately; abandoned/interrupted uploads are bounded by expiry. Saved models never expire. A future inference runner must hold/renew the model lease for the duration of a run.

Inspection metadata additionally exposes nullable `model_series`, `series_source` and `ultralytics_version`, separate from broad `family` and `scale`. SQLite inspection JSON retains these fields without a schema migration. Re-inspect previously stored results to populate them.

New source uploads store `metadata.sha256` for the original bytes, computed incrementally during upload, and `preview_size` when a preview sidecar is created. No extra file pass or schema migration is needed. Existing source records remain unchanged and may lack these fields.

## Image inference runs

Start backend 8000 and AI 8001 with the same `VISIONKIT_MODELS_PATH` and `VISIONKIT_RUNS_PATH` (default root `data/models`, `data/runs`). Migration 5 creates the `runs` table. Backend imports no Torch/Ultralytics. Model download/inspection and source APIs remain separate.

- `POST /api/v1/runs`: multipart `model_id`, `options` JSON, and exactly one of uploaded `file` or saved `source_id`; returns 202 with a run. Images, screenshots and video files. Unsaved multipart uploads additionally set `kind=image|screen|video`; saved source IDs determine their kind. Options: numeric `conf`, `iou`, two-element `[height,width]` `imgsz`, `device`, optional class IDs, `max_det`, `agnostic_nms`, and video `vid_stride` (1–120).
- `GET /api/v1/runs/{id}`: latest state/result; `DELETE` cancels an active run.
- `GET /api/v1/runs/{id}/preview`: browser-compatible snapshot used for result display.
- `WS /api/v1/runs/{id}/events`: immediate/current snapshot and updates until terminal; allowed Origin must match backend CORS settings. Client can reconnect or fall back to GET. WebSocket closure alone does not cancel inference.

States: queued → running → completed/failed/cancelled. At most four active/queued runs, one outbound inference request at a time per backend worker. Use one Uvicorn worker for the MVP. Active models are pinned against deletion/temporary-model cleanup; cancelling releases the lease. Input images are copied into run storage, so deleting a library source cannot remove an active run input. Uploading an unsaved image for a run does not save it to the Source library. Failed creation rolls back the snapshot. Repeated POST creates a new run; uploads do not resume across a lost response.

Run snapshots and result JSON expire after 24 hours. Startup and a ten-minute sweep clean expired terminal records/files. Expired records return 410 before cleanup, 404 after; saved library sources/models are unaffected. Backend restart marks interrupted jobs failed. These local DB/file operations are not atomic across power failure; orphan reconciliation remains future work.

Completed JSON contains original-coordinate bbox/keypoints, class scores, actual device, timing and classification top5. Segmentation/OBB polygons are retained in JSON; current canvas UI displays bbox/keypoints only. RTSP inference uses the separate stream-run endpoint below. Webcam inference, tracking, model prompting and a persistent run library are not implemented.

## Streaming video runs

Video inputs use the same run routes and 24-hour snapshot retention as images, with existing video validation, original copy and thumbnail generation. `GET /runs/{id}/preview` returns the original video (not the JPEG thumbnail), with HTTP Range for browser playback. Source-library records are unchanged.

Backend consumes AI NDJSON as it arrives, keeps one latest frame per active run and publishes snapshots through the existing WebSocket (up to about 20 snapshots/s; intermediate frames can be dropped for a slow consumer). Only the latest result is retained, with SQLite checkpoints at most once per second and a final terminal write. No per-frame timeline or annotated-video artifact is stored. Frame IDs, timestamps, counts, FPS and percent appear under `result`/`progress`. An error/early stream EOF is failed rather than completed, retaining the last partial frame; cancellation similarly retains the last progress and releases the model lease.

The backend explicitly depends on `websockets` for Uvicorn's WebSocket runtime. `uv sync` then restart/reload the backend after dependency changes; Next forwards the same-origin `/api/v1/runs/{id}/events` upgrade. HTTP polling remains a fallback when a deployment proxy blocks WebSockets. One backend and one AI worker are recommended for the in-process MVP queue.

## Centralized runtime logs

`GET /api/v1/logs` is the read API used by the workspace runtime log viewer. A separate backend task collects AI logs every second, independently of
inference and browser connections. Existing terminal handlers remain in place.
Capture includes Python `app` logs, Uvicorn server/access logs and AI worker stderr;
it is not a mirror of arbitrary OS terminal output.

| Query | Behaviour |
|---|---|
| `after` | Opaque `next_cursor` from the previous response; omit on first read or filter change |
| `limit` | Matching entries per page, default 200, range 1–500 |
| `service` | Optional `backend` or `ai`; omit for both |
| `min_level` | DEBUG, INFO (default), WARNING, ERROR, CRITICAL; capture starts at INFO |
| `run_id` | Optional UUID to follow one inference run across services |

Example: `/api/v1/logs?service=ai&min_level=WARNING&limit=100`.
Each item has `id`, `timestamp` (UTC), `service`, `level`, `logger`, `message`,
nullable `run_id`, nullable `traceback`, and nullable `source_id` (original AI ID).
The merged `id` follows backend ingestion order; AI timestamps are preserved and
can arrive later than backend timestamps. Do not use timestamp as a cursor.

The response contains:

- `items`, `next_cursor`: append items and pass the cursor unchanged on the next
  request, even if items is empty. Reset pagination when changing filters.
- `has_more`: drain remaining pages, then poll about once a second.
- `reset`: backend session changed or cursor is ahead; discard old pagination state.
- `dropped`: unread entries were evicted from the backend buffer.
- `ai.configured`, `ai.available`: configured flag and null before first attempt,
  false on collection failure, true on success. Backend logs stay readable offline.
- `ai.last_success_at`: last successful collection timestamp, initially null.
- `ai.reset_count`, `ai.dropped_batches`: cumulative AI restart/gap counters,
  separate from backend cursor gaps. Both start at zero.

Inference sends `X-VisionKit-Run-ID` to AI; both services tag task logs with that
UUID without changing inference JSON contracts. General startup/access/model
inspection logs may have null `run_id` and remain visible without that filter.

Each service uses a **RAM ring of 2,000 entries**, with message and traceback each
capped at 8,192 characters. Restart loses local history; there is no log archive
in SQLite or files. Run **one Uvicorn worker per service** for this MVP. The
collector fetches at most four pages of 500 entries per cycle.

Worker stderr is drained concurrently in bounded chunks, recorded as INFO, with
at most 20 entries/second per worker plus a warning counting omitted entries.
Structured image/video/inspection failures are ERROR, with a bounded, redacted
`traceback` on the same log entry when the worker caught an exception. This entry
is independent of stderr throttling, so an ERROR filter retains the diagnostic
traceback. Raw stderr remains INFO. Backend video progress is logged at most
once every five seconds plus completion. No per-detection log is generated and
this feature does not change inference pacing.

Health/log polling access logs are excluded to prevent self-generated noise.
Responses use `Cache-Control: no-store`. Common credential patterns are redacted
and terminal control sequences stripped; callers must still avoid logging secrets.
AI logs remain on its loopback/internal API; the web only calls backend and needs
no direct AI connection. Logs follow the current local API trust model.

### Web viewer integration

- Use only the backend `/api/v1/logs` endpoint through the existing web proxy.
  Worker traceback details belong to this API; inference response schemas stay unchanged.
- Keep at most 2,000 displayed entries and use `id` as the row/deduplication key.
  Advance `after` from every successful response, including empty pages. Reset
  cursor and displayed entries when filters change or the server returns `reset`.
- Fetch sequentially, drain `has_more` pages, then poll about once per second.
  Abort pending fetches on unmount/filter change and pause polling in hidden tabs.
  Cancel scheduled retries on unmount; avoid overlapping requests.
- Show backend `dropped` gaps and changes in AI `reset_count`/`dropped_batches`.
  Treat `ai.available: null` as not yet checked and `false` as unavailable; keep
  backend logs visible. On HTTP/network errors, retain entries/cursor and retry
  with bounded backoff. Render messages/tracebacks as text.

Image and inspection worker stdout is capped at 8 MiB; video retains its 8 MiB
per-event cap. Overflow fails the operation and reaps the worker while draining
remaining pipes in bounded chunks. These limits bound transport buffers, not
model inference RAM/VRAM. Backend lifespan cleanup also runs after partial startup
failure, and unused model lease counters are removed when their count reaches zero.

## Nguồn RTSP và API lượt chạy live

Backend đã hỗ trợ lưu cấu hình RTSP/RTSPS và điều phối inference qua endpoint
nội bộ riêng của AI. Web đã có chọn nguồn và preview WebRTC qua MediaMTX;
phần khởi chạy inference RTSP trên web chưa được nối.
Không cần migration: bảng `sources` đã có kind `stream`, run lưu JSON có default
cho trường mới nên ảnh/video cũ vẫn đọc được.

### Lưu và sửa camera

```http
POST /api/v1/sources/rtsp
Content-Type: application/json

{"name":"Camera cổng","url":"rtsp://user:password@192.168.1.10:554/live"}
```

Trả `201 SourceResponse`, kind `stream`; `content_url`/`preview_url` là `null`.
`location` chỉ là **nhãn đã che credentials và query**, không dùng nhãn này để
kết nối lại hoặc điền mặc định rồi gửi form chỉnh sửa. URL gốc được lưu trong
SQLite local để backend cung cấp cho AI; chưa có mã hoá bí mật trong DB.

- `PUT /api/v1/sources/{id}/rtsp`: JSON cùng cấu trúc, thay đầy đủ tên/URL camera.
- `GET /api/v1/sources?kind=stream`: danh sách dùng response đã che.
- `GET /api/v1/sources/{id}`, `PATCH /api/v1/sources/{id}` (đổi tên),
  `DELETE /api/v1/sources/{id}`: dùng API nguồn hiện có.
- Tạo cấu hình không mở camera. Sửa URL cập nhật path preview đang hoạt động;
  trạng thái/xác thực đọc qua API preview, không suy đoán từ việc lưu thành công.
  URL chỉ nhận `rtsp://`/`rtsps://`, có host/port hợp lệ, không fragment/control/space.
- Không nhận HTTP/RTMP/YouTube/file qua API này. Nguồn LAN/private IP là hợp lệ.
- Lỗi validation chỉ trả vị trí/loại lỗi, không phản chiếu giá trị đầu vào.

### Chạy suy luận

```http
POST /api/v1/runs/stream
Content-Type: application/json

{
  "model_id":"<model-id>",
  "source_id":"<source-uuid>",
  "options":{"device":"auto","imgsz":[640,640],"vid_stride":1},
  "duration_seconds":3600
}
```

Trả `202 RunRecord`; options giống ảnh/video. Model phải sẵn sàng và class/imgsz
hợp lệ. Không nhận URL trực tiếp, chỉ nhận source ID đã lưu. `duration_seconds`
là số nguyên 1–14400, mặc định 3600 giây; tính sau khi model/capture đã mở,
không tính thời gian chờ hàng đợi và cold load. Native read/inference cuối cùng
có thể khiến terminal trễ thêm so với thời hạn này.

Dùng tiếp các API sẵn có:

- `GET /api/v1/runs/{id}` hoặc WebSocket `/api/v1/runs/{id}/events`: snapshot mới
  nhất, `source_kind="stream"`, `progress.is_live=true`, `percent=null`,
  `total_frames=null`; không lưu timeline/frame nhị phân. `source_fps` có thể
  `null` khi camera không cung cấp; `processing_fps` là FPS suy luận thực tế.
- `DELETE /api/v1/runs/{id}`: dừng run, huỷ HTTP AI và kill/reap worker.
- Đến hạn: `completed`, `completion_reason="duration_limit"`. Mất camera/stream
  EOF trước terminal: `failed`. Chủ động dừng: `cancelled`. Frame cuối được giữ.
- `/runs/{id}/preview` không vận chuyển video live: trả 404 với
  `source_metadata.preview_available=false`. Web xem video qua MediaMTX/WebRTC
  độc lập với run events. Không trả URL/password qua run JSON hay WebSocket.
  Khi nối inference RTSP lên web cần xử lý `source_kind="stream"` và nullable FPS.

URL camera được snapshot riêng trong task lúc tạo job. Sửa/xoá source không đổi
URL hoặc tự dừng job đang chạy; muốn dừng phải cancel run. Backend restart đánh
live job chưa xong thành failed; không tự kết nối lại camera. Run terminal vẫn
hết hạn/dọn sau 24 giờ nhưng không có file media để xoá.

RTSP dùng chung giới hạn hiện tại: tối đa bốn job active/queued, một inference
đồng thời. Một live run dài sẽ giữ lượt xử lý; các job ảnh/video khác phải chờ.
API này dành cho workspace local hiện có; service AI chỉ để backend truy cập.

### Kiểm chứng

`tests/runs/test_rtsp.py` dùng DB/storage thật và HTTP AI giả lập để kiểm CRUD,
validation/redaction, định tuyến payload, snapshot, WebSocket, cancel/lease,
queue, EOF/error, expiry và restart. Bộ AI có test contract/adapter/worker riêng.
Đã smoke test RTSP H264/RTP interleaved TCP từ fixture loopback với YOLO26s thật
trên CPU/CUDA, gồm hết hạn, cancel và camera không kết nối được. Đây chưa phải
kiểm chứng camera vật lý, RTSPS/TLS hoặc soak nhiều giờ.

## Preview RTSP qua MediaMTX / WebRTC

Backend không giải mã video, không tạo JPEG và không proxy RTP. MediaMTX v1.21.3 chạy Docker
kéo RTSP/TCP bằng URL từ source DB, chia sẻ một path/camera và chuyển tiếp codec
sang WebRTC. Browser dùng WHEP signaling qua backend rồi nhận media trực tiếp từ
MediaMTX. Cài relay/chạy local theo README gốc.

- `POST /api/v1/streams/temporary/sessions`: JSON `{preview_id: UUID, url: RTSP}`,
  tạo lease để kiểm tra URL chưa lưu và phát WebRTC khi MediaMTX đọc được luồng.
  Không cần tên/source ID đã lưu; không tạo bản ghi Source, không ghi URL vào DB.
  URL chỉ giữ RAM/MediaMTX đến khi lease cuối đóng/hết hạn. Dùng namespace riêng
  và giới hạn bốn path chung; lỗi validation không phản chiếu credentials.
- `POST /api/v1/streams/{source_id}/sessions`: tạo lease, đăng ký path nếu cần;
  response có `id` và URL WHEP cùng origin, không có URL/password camera.
- `GET /api/v1/streams/sessions/{id}`: gia hạn lease 45 giây và trả trạng thái,
  `auth`, codec, lỗi đã phân loại. Web poll tuần tự mỗi hai giây.
- `POST /api/v1/streams/sessions/{id}/whep`: `application/sdp` tối đa 256 KiB;
  trả SDP answer. Backend giữ WHEP Location và chỉ nhận cùng origin/path relay.
- `DELETE /api/v1/streams/sessions/{id}`: đóng WHEP; viewer cuối gỡ path/ngắt RTSP.
  Browser biến mất thì task dọn lease mỗi năm giây. Tối đa bốn path camera.

Camera chỉ được báo đọc thành công khi `available/ready` của Control API là true;
`online` không đủ. API `paths/static-sources/get` có `lastError`: 401/403 được
phân loại `auth_failed`, không retry vô hạn. Lỗi mạng là trạng thái chưa xác minh,
MediaMTX tiếp tục reconnect. Không suy đoán mật khẩu đúng từ URL hoặc việc online.
Không trả raw lastError/config MediaMTX ra browser/log vì có thể chứa credentials.
Đọc được camera anonymous cũng là `auth=accepted`, không chứng minh đã dùng password.

Sửa URL khởi động lại path preview, giữ các lease. Xoá camera đóng mọi lease của
camera đó. Các inference run vẫn dùng reader/URL snapshot độc lập như trước.
Backend restart mất registry lease; nên chạy cùng lifecycle launcher MediaMTX.
Dùng một backend worker; không chia sẻ relay namespace `visionkit_*` với backend
khác. Biến `VISIONKIT_MEDIAMTX_API_URL` / `VISIONKIT_MEDIAMTX_WEBRTC_URL` chỉ trỏ
HTTP service nội bộ, mặc định loopback 9997 / 8889. API MediaMTX không công khai.

`tests/streams` có unit contract/lease/redaction và integration MediaMTX thật với
camera H264/TCP Basic auth loopback, gồm credentials đúng/sai và sửa URL phục hồi.
FFmpeg chỉ tạo bitstream fixture rồi thoát, không chạy trong pipeline preview.
Chưa kiểm camera vật lý, RTSPS/TLS hoặc network soak nhiều giờ.

Relay Docker dùng image chính thức đã pin digest trong `compose.yaml`. Launcher
chỉ quản lý container/network của project hiện tại, không mount dữ liệu camera,
model hoặc database vào container. Port host chỉ publish trên loopback. Khi dùng
launcher, URL camera loopback được ánh xạ nội bộ sang `host.docker.internal`; URL
đã lưu trong DB không bị sửa. `VISIONKIT_MEDIAMTX_SOURCE_HOST` cấu hình host này
cho relay quản lý ngoài launcher. Bật `VISIONKIT_RUN_DOCKER_TESTS=1` để chạy test
integration Docker, gồm camera RTSP Basic auth đúng/sai, sửa URL và cleanup.

## AI through the shared RTSP relay

`POST /api/v1/runs/live` accepts `model_id`, exactly one `source_id` or `preview_id`,
`options` and `duration_seconds` (1–14400, default 3600). The preview ID must belong
to a temporary session created by the RTSP check flow. Backend keeps a separate
MediaMTX path lease for AI, then passes `VISIONKIT_MEDIAMTX_RTSP_URL/visionkit_<id>`
(or `visionkit_temporary_<id>`) to the internal AI stream API. Only MediaMTX opens
the original camera; browser and AI read the same relay. The run record contains
IDs and JSON metadata, never camera credentials or video frames.

The AI lease survives browser viewer expiry and route navigation. Terminal,
cancel, failed validation and shutdown release it; the last lease removes the
path and temporary URL. Editing/deleting a saved camera with active relay AI
returns 409. `options.max_fps` limits live inference to 1–60 FPS (default 5).
The older `/runs/stream` endpoint remains a direct-camera compatibility API;
the web uses `/runs/live`. JSON run events use the existing WebSocket, with GET
polling fallback. Inference concurrency remains one: additional runs queue.
