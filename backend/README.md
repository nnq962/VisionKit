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

POST `/api/v1/models/upload` accepts multipart `file` (`.pt` or `.onnx`), optional `name` (1–120 characters), `family=yolo|yoloe`, and `task=detect|segment|pose|classify|obb`. Defaults are `family=yolo` and `task=detect`; YOLOE requires `task=segment`. The backend writes in chunks, computes SHA-256, assigns a UUID and stores the original filename and declared metadata in the existing `models` table. Custom models have `variant.origin=upload`, `variant.size=null`, and optional catalog URL/release fields. Existing catalog models remain compatible; no new migration is needed.

Upload defaults to **200 MiB**, configurable with `VISIONKIT_MAX_MODEL_UPLOAD_MB`. GET `/api/v1/models/catalog` returns `max_upload_bytes` for the picker. The web proxy currently allows 210 MiB; raise it alongside the backend setting if needed. Invalid extension returns 415, empty/invalid form 422, oversized file 413. Failed DB inserts remove newly uploaded files. Duplicate filenames receive separate IDs/paths and never overwrite existing weights.

This endpoint stores user-declared model files. It does **not** deserialize PyTorch checkpoints, parse ONNX graphs, or verify that the file is an Ultralytics model. Compatibility, actual task detection and inference belong to the AI module. GET `/api/v1/models/{id}` checks that a saved model's file still exists and has the recorded size (404/409 otherwise); the pipeline calls it before advancing from model selection. This check is not a full checksum rescan or an inference test.

The web picker supports saved models and custom upload, shows real browser upload progress, and selects the new model only after HTTP 201. The selected model ID and upload draft (File plus declared metadata) persist in browser IndexedDB across steps/routes/reload. Unsaved file drafts remain local until the user presses **Lưu và chọn**. If browser storage fails, the web reports it and warns before leaving with an unpersisted file. Active uploads warn before reload; upload requests themselves do not resume after reload. Model Hub and the picker read the same backend library.
