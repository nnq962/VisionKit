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

Images are checked by decoded content, not by their filename or declared MIME. Supported image formats: JPEG, PNG, WebP, GIF, BMP, AVIF, HEIC/HEIF, subject to Pillow codec support. Default limits: 20 MiB/file and 64 million pixels. Metadata includes displayed width/height (respecting EXIF orientation), file size, actual format/MIME and original filename. File names on disk are generated UUIDs. Saving RTSP and AI processing are not implemented by these APIs yet.

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

Completed JSON contains original-coordinate bbox/keypoints, class scores, actual device, timing and classification top5. Segmentation/OBB polygons are retained in JSON; current canvas UI displays bbox/keypoints only. No RTSP/webcam inference, tracking, model prompting or persistent run library yet.

## Streaming video runs

Video inputs use the same run routes and 24-hour snapshot retention as images, with existing video validation, original copy and thumbnail generation. `GET /runs/{id}/preview` returns the original video (not the JPEG thumbnail), with HTTP Range for browser playback. Source-library records are unchanged.

Backend consumes AI NDJSON as it arrives, keeps one latest frame per active run and publishes snapshots through the existing WebSocket (up to about 20 snapshots/s; intermediate frames can be dropped for a slow consumer). Only the latest result is retained, with SQLite checkpoints at most once per second and a final terminal write. No per-frame timeline or annotated-video artifact is stored. Frame IDs, timestamps, counts, FPS and percent appear under `result`/`progress`. An error/early stream EOF is failed rather than completed, retaining the last partial frame; cancellation similarly retains the last progress and releases the model lease.

The backend explicitly depends on `websockets` for Uvicorn's WebSocket runtime. `uv sync` then restart/reload the backend after dependency changes; Next forwards the same-origin `/api/v1/runs/{id}/events` upgrade. HTTP polling remains a fallback when a deployment proxy blocks WebSockets. One backend and one AI worker are recommended for the in-process MVP queue.
