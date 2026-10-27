# VisionKit Web

Next.js App Router, TypeScript, Tailwind CSS, shadcn/ui (Radix), and Manrope.

## Development

```bash
npm install
npm run dev
```

## Routes and organization

```text
src/
  app/
    layout.tsx                  # Fonts, metadata, global providers
    page.tsx                    # Redirect / to /database
    (workspace)/                # Shared sidebar layout; absent from URLs
      layout.tsx
      database/page.tsx         # /database
      pipelines/yolo/page.tsx   # /pipelines/yolo
    dashboard/page.tsx          # Redirect the original demo URL to /database
  features/
    pipelines/yolo/             # YOLO-specific UI and configuration flow
  components/
    app-sidebar.tsx
    workspace-header.tsx
    ui/                         # shadcn primitives
  lib/navigation.ts             # Sidebar links and active route matching
```

Add workspace routes under `src/app/(workspace)/` to reuse the sidebar. Keep feature-specific components under `src/features/<feature>/` and add navigation entries in `src/lib/navigation.ts`.

Database manages the saved source library. The YOLO picker connects source and model storage to the backend; model metadata is extracted by the separate AI service. Image and video-file inference are connected to the separate AI service.

## Checks

```bash
npm run lint
npm run build
```

## Source API integration

Run the backend on port 8000 before using the persistent library. Next.js proxies `/api/v1/*` to `http://127.0.0.1:8000`; set `VISIONKIT_API_URL` in the web server environment to use another backend address. Restart Next.js after changing its configuration/environment.

Images and one-shot screen captures preview locally first. Selecting “Lưu source để tái sử dụng” uploads the actual file and persists metadata; the saved library survives page reloads. It supports previews, rename, confirmed deletion and loading additional pages. Search filters currently loaded entries. Video files also support persistent upload and inference. RTSP, YouTube video and local webcam inference are documented below.

`src/features/sources/api.ts` owns the HTTP contract. The reusable source module handles metadata, browser capture and library state; the four YOLO step components remain separate. The UI reports API errors and retries without falling back to sample data.

HEIC/HEIF files use the backend's transient `/api/v1/sources/inspect` endpoint for preview before saving, since browser HEIC decoding varies. This uploads temporarily but does not add to the saved library. After saving, `preview_url` displays a JPEG sidecar while the backend retains the original HEIC bytes. JPEG iPhone images continue to work with the normal local preview flow.

## Source drafts

`SourceProvider` lives in the shared workspace layout so changing routes does not destroy the current source picker state. `use-source-drafts.ts` keeps independent drafts for each source type, including the original File, HEIC preview Blob, URL text, display name and save preference. Selecting an existing library source does not replace a new-source draft.

Draft files and metadata are saved locally in IndexedDB (`visionkit-source-drafts`), not automatically uploaded to the saved library. Blob preview URLs are reconstructed after reload. A draft remains local to this browser/origin and can be explicitly discarded; saving to the backend removes it from the unsaved draft cache. Browser storage is best-effort: if unavailable/full, the UI reports that drafts are only retained during in-app navigation and warns before leaving/reloading. Files interrupted during metadata reading are retained with a retry action. Screen MediaStreams are never persisted. Webcam capture belongs to the AI worker on the server; the browser does not call getUserMedia. RTSP WebRTC connections are owned by the root provider and remain connected across routes until explicitly stopped.

## Model Hub

`/models` reads its catalog, saved model library and download jobs from `/api/v1/models`. Download progress uses actual backend byte counts; jobs survive navigation and reload, and can be cancelled or retried. Completed downloads are saved in backend SQLite/storage. There is no browser-only mock download or localStorage model library. Backend startup and model API details are documented in `../backend/README.md`.

## Pipeline model selection

The YOLO model step uses the real `/api/v1/models` library, or uploads custom `.pt`/`.onnx` weights via `/api/v1/models/upload`. It selects saved model IDs, validates file availability before advancing, and displays browser upload progress. Reusable components and the selection provider live in `features/models/`; `steps/model-step.tsx` only composes them. IndexedDB retains model selection and unsaved upload drafts across routes and reloads. Runtime compatibility remains the responsibility of the AI module.

Run the AI service on port 8001 alongside backend 8000. Selecting a file automatically uploads it to temporary storage and polls metadata extraction; no save click is required. **Lưu vào thư viện** promotes the same file without uploading it again. The pipeline can advance with a temporary model after metadata is ready/manual. Temporary models are hidden from the saved library, survive reload via their IndexedDB ID, and expire after 24 hours of inactivity. Details show inferred family/task, class names/count, image size, input shape and available architecture information. Missing metadata allows manual configuration; AI downtime preserves the uploaded model with a retry action. Existing uninspected models are inspected on selection. The next step requires `ready` or explicit manual configuration; extracted metadata does not validate inference execution.

## Database models

`/database` switches between Source and Model libraries. The Model view reads the same saved `/api/v1/models` records as Model Hub, excluding temporary uploads. It supports client-side search, PT/ONNX filters, progressive display, storage totals and a details sheet with metadata, ID, relative storage file, exact bytes, save time and full SHA-256. Metadata can be re-read or supplemented through the existing model APIs, independently of the current pipeline selection. The catalog refreshes every four seconds and on focus/model changes. Components and data state live under `features/database/`; the route only composes the workspace.

Source and model detail sheets share `StorageDetails`. Saved sources expose original filename, relative storage location, exact bytes, MIME, created/updated timestamps, optional preview file/size and SHA-256. New image/screen/video uploads compute SHA-256 while streaming; older records without it display “Chưa ghi nhận”.

## YOLO parameter setup

The Parameters step composes inference controls, a searchable metadata-driven class filter, collapsible advanced settings and a source/model context panel. Confidence/IoU, input dimensions, requested device, maximum detections, class-agnostic NMS and temporal frame stride are represented as configuration. Classification hides bbox/NMS/class-filter controls. Static NCHW ONNX spatial dimensions lock the input size (including rectangular inputs); other size options follow the model stride. Runtime hardware support is still unverified until inference integration.

`parameters.ts` owns defaults/constraints and labels, `use-pipeline-parameters.ts` persists configuration per model ID in browser localStorage with an in-memory fallback, and `components/parameters/` holds class filtering and context. The Run step reviews the same values; execution is connected to the inference API for images and video files. Stored parameters are a browser draft, not a saved backend pipeline.

## Reusable vision overlay

`features/vision-overlay` provides `useDetectionOverlay` and `DetectionMedia` for bbox/keypoint canvas overlays on images or videos. It handles contain/cover/fill geometry, optional mirroring, normalized or original-pixel coordinates, Retina scaling, resize, labels, configurable skeletons and optional stale-result clearing for live feeds. The Run step feeds real inference results into this overlay; no sample detections are added to product routes. See `src/features/vision-overlay/README.md` for the coordinate contract and examples. Run `npm run test:overlay` on Node >=22.18 for geometry tests.

## Real image inference

The Run step now starts real image/screenshot/video-file inference through `features/inference/`. It uploads unsaved original files or references saved sources, requests the selected stored/temporary model and numeric parameters, then subscribes to run WebSocket events with a GET polling fallback. Results feed the reusable canvas overlay, a detection/classification list and JSON download. The user can stop/retry and toggle annotation visibility. The latest run ID for the same source/model/options is remembered in sessionStorage for tab-local reload/navigation recovery; snapshots expire after 24 hours. A changed configuration requires a new run. RTSP inference uses the live relay flow below; local webcam inference is documented below.

Run both backend 8000 and AI 8001; install AI dependencies with `cd ai && uv sync`. Actual device availability is validated in AI. ONNX runs on CPU in this MVP. Segmentation/OBB polygons are in downloaded JSON while preview shows bbox; pose keypoints display without guessing a custom skeleton. No inference output is mocked in product routes.

## Video inference preview

The shared `RunWorkspace` / `useInferenceRun` supports uploaded or saved video files alongside images. The request passes the configured `vid_stride`; real WebSocket snapshots update a latest-frame canvas, progress bar, processed count and FPS. Playback starts with the first AI result, muted, without seek controls. On an active-run reload it initially positions near the current AI timestamp; it does not keep a result timeline or continuously synchronize clocks. Stopping inference pauses playback. In the current run view, terminal results remain paused near their final AI timestamp
and their overlays do not expire. Returning to step 4 after leaving it resets a
finished/cancelled/failed video to the initial preview, ready for a new run, without
restoring old progress or annotations. Queued/running video runs still reconnect;
image results retain their existing restoration behavior. JSON download contains the last frame and summary only, not all video detections.

Browsers must support the original codec (MP4/H.264 is practical); no transcoding is done. Bbox/keypoint output can lag or lead playback, especially on slow hardware. Frames with no objects clear prior annotations, stale active overlays expire, and overlays are hidden after playback ends while AI is still working. Source video itself is never sent frame-by-frame from AI to the browser. Canvas and video playback remain separate.

## Run overlay controls

The result sidebar now contains independent Bounding box, class/confidence label, keypoint-dot and skeleton toggles instead of a continuously changing object list. Preferences persist locally across runs/reload and apply to the canvas only; toggling never re-runs inference or seeks video. Classifier output retains its top prediction as a compact summary.

Pose previews default to the COCO 17-keypoint skeleton preset; a detected non-17 schema disables this preset rather than guessing connections. Points and connecting edges can be shown independently (e.g. skeleton-only with bbox hidden). Empty COCO pose frames keep the configured controls stable and clear the canvas as usual. Other skeleton layouts can be passed through the reusable overlay hook when their schema is configured. The existing confidence/visibility checks also suppress edges whose endpoints are missing or low-confidence.


## Runtime log window

The header Log button opens a draggable, resizable, non-modal window on every workspace
route. It reads real backend/AI logs from `/api/v1/logs` through the Next.js proxy.
There are no sample entries. Source, level and text filters apply to the latest
2,000 retained entries; the error filter includes CRITICAL. Search also matches
logger, traceback and run ID. Timestamps use the browser's local timezone.

Polling is sequential (500 entries/page), drains `has_more`, then waits one second.
A failed request retains entries/cursor and retries with backoff capped at 30s.
Requests time out after 5s. Closing, pausing, hiding the tab or unmounting aborts
in-flight reads and clears scheduled reads; resuming continues the same cursor.
Clear affects only displayed entries; previously consumed logs are not reloaded.
Backend restart resets the displayed session; overwritten unread logs and AI
history gaps show a dismissible notice. AI availability is displayed independently
of backend connectivity. Log text is rendered as text, never HTML.

Run `npm run test:logs` (Node >=22.18) for bounded retention, pagination, cursor,
abort/late-response, reconnection and history-reset regression coverage.

The log window supports resizing from all four edges and four corners, including
touch input. Its minimum size is 360 × 300 px (reduced on smaller screens); resize
stops 12 px from the viewport edge. Controls adapt to the panel width. Position
and custom size survive closing and workspace navigation; the expand button
restores the previous custom size when toggled back. The bottom-right handle also
supports arrow keys, with Shift for larger steps. Size/position reset on reload.

## Persistent RTSP preview hook

`features/video-stream` exports `useVideoStream(sourceId)` and `VideoStreamPreview`.
The root `VideoStreamProvider` shares one RTCPeerConnection and MediaStream per
camera/temporary preview ID. It retains the peer across route and step changes,
checks connection state and API heartbeat, and releases it on explicit stop or
provider teardown. Preview uses WHEP signaling and native `<video>` playback;
MediaMTX sends the media directly to the browser. Python does not transport frames.
See `src/features/video-stream/README.md` for usage, lifetime, limits and tests
(`npm run test:streams`).

## RTSP camera configuration

The Source picker and Database share a camera form with a name, masked/revealable
RTSP/RTSPS URL, validation and a credential-free host/port summary. “Kiểm tra và
xem trực tiếp” checks an unsaved URL and starts WebRTC after MediaMTX confirms
readable media. Name is optional for this flow; it creates no library source.
“Lưu vào thư viện” is a separate optional action requiring a name. Saved cameras expose “Sửa cấu hình”;
a replacement URL starts empty, and leaving it empty renames the camera without
changing its connection details. Saving a replacement URL restarts the shared
preview reader while retaining its viewers. Existing inference runs are unaffected.
Database supports adding/filtering RTSP cameras and editing/deleting their
configuration. Preview shows connecting/playing/reconnecting/stopped/error states
and manual stop/reconnect controls; stopping survives route changes.

Camera access feedback comes from MediaMTX ready/source-error APIs; account
detection in the configuration form is only a URL summary. RTSP form handling is
separate from YouTube URL selection and file upload. Camera create/update APIs
receive the original URL from the form; redacted display locations are never used
to save credentials. See the root README for Docker relay setup, codec constraints
and local ICE networking.

## Live RTSP inference

After checking an unsaved camera or selecting a saved camera, select a model and
continue to Run. `POST /api/v1/runs/live` receives a source ID or temporary preview
ID, never the camera URL. Video keeps playing from the shared WebRTC peer while
JSON results draw boxes/keypoints on a separate canvas. Expire stale annotations
after two seconds. Video and AI are asynchronous, so boxes can lag slightly.

AI defaults to a maximum of 5 FPS and 60 minutes; both are adjustable in Parameters
(1–60 FPS, 1–240 minutes). Navigation unmounts only the observer; the server run
continues. Returning to Run with the same source/model/options restores its ID
from sessionStorage and resumes results/Stop. Dừng AI cancels inference while
WebRTC video keeps playing. Closing the tab does not cancel AI: it stops at the
duration limit or explicit API cancellation. Backend restart interrupts active runs.

## YouTube video source

Choose YouTube, paste a single video link and select **Chuẩn bị video**. This
creates a temporary preparation job, shows preparing/error/ready status, then
provides native video preview with seeking. **Huỷ chuẩn bị / Xoá video tạm**
cancels or deletes the job. Public ordinary videos are supported; Live and
scheduled videos are rejected. Preparation uses at most 720p H.264 MP4 and the
backend byte cap (default 200 MiB); the cache expires after an hour without use.

Continue with a model and parameters to run the existing video inference flow.
AI always starts from the beginning, independently of seeking in source preview.
The selected job and active run survive in-app routes; reload rechecks the job,
and an expired or restarted backend prompts preparation again. Stop/retry,
per-frame annotations, progress and JSON download work as for local video files.
Nothing is automatically added to the saved source library.

`npm run test:youtube` checks session metadata mapping, prepared-session run
requests and active/finished run recovery. Backend tests also cover file Range,
cancellation/reaping, timeout, cache expiry, input validation and run snapshots.

## Webcam on the AI host

This feature is intended for a browser running on the same machine as the server.
Choose Webcam / USB, enter the OpenCV device index (default 0, allowed 0–15) and
select Kiểm tra webcam. The AI process opens one frame and releases the camera;
the returned image is a check snapshot. Browser camera permission/device IDs are
not used. Starting inference opens that integer device directly in the YOLO worker.

The worker keeps one capture and uses the newest frame, capped by live FPS and
duration settings. For webcam only, it also creates a JPEG from the same frame
(maximum 960px, quality 70). Backend retains only a bounded latest-frame cache in
RAM and serves JPEG by HTTP; run WebSocket/JSON and SQLite never contain images.
The preview follows AI FPS, so it is a results preview rather than a separate
full-rate video stream. MediaMTX is not involved. Navigation/reload can restore
an active run with the same selection/options. Stop reaps the worker and releases
the webcam; checking again should succeed. Webcam images are not persisted in drafts.

Webcam startup now discards frames for approximately one second before the check
snapshot and live inference, allowing camera exposure to settle. The webcam run
preview keeps one canvas, decodes JPEGs offscreen and atomically paints image plus
annotations. Slow/failed image requests retain the last good frame; pending
updates coalesce to the newest URL instead of rebuilding the image/canvas DOM.

## Completing a pipeline and source controls

The Run step shows **Hoàn thành** after completion, failure or Stop. Completion
awaits cleanup, clears the run recovery ID, releases the selected RTSP viewer or
YouTube cache, revokes draft object URLs and clears the current source selection,
then returns focus to step 1. Temporary uploaded models are deleted; saved source
and model library entries and other drafts are preserved. Cleanup errors keep the
run step visible for retry. JSON can be downloaded before completion; finishing
removes the run snapshot/result rather than retaining it for the usual 24 hours.

Saved sources have type filters and grouped headings. Type/name searches and
pagination use the backend API, including sources beyond the first 50 entries.
Confidence and IoU use keyboard-accessible native sliders (0–1, step 0.01) paired
with numeric inputs for precise entry. The floating log window has a compact
single-row title/actions header and responsive filter/search toolbar; dragging,
resizing, pause, clear and filtering remain available.

## YOLOE text prompt

Trong YOLO pipeline, chọn YOLOE `.pt` rồi mở Thông số. Có sẵn 22 vật thể thường
gặp: người, xe, laptop, màn hình, điện thoại, đồ gia dụng và chó/mèo. Bấm một gợi ý
để thêm/bỏ, hoặc sửa tên tiếng Anh trong ô prompt (dấu phẩy/xuống dòng). Dùng gợi ý
khôi phục bộ mặc định; Xoá hết để tự nhập danh sách mới. Giới hạn 80 prompt.
Danh sách lưu theo model trên trình duyệt; run lưu snapshot trong backend. Thay đổi
prompt tạo cấu hình chạy mới; không sửa run đang chạy. Nhãn kết quả dùng tên đã nhập.
Không dùng bộ lọc class metadata của model khi chạy text prompt. Chuẩn bị text
encoder theo `ai/README.md`; ONNX/prompt-free/fused chưa hỗ trợ đổi prompt.

Kiểm tra contract và payload cho mọi loại nguồn: `npm run test:yoloe`.

Trong bước Chạy, mục Hiển thị có tuỳ chọn Segmentation cho model segment (YOLO và
YOLOE). Mask được tô bán trong suốt theo màu class, độc lập với Bounding box;
mask/box/nhãn dùng cùng phép chiếu và clipping của ảnh/video. Tuỳ chọn được giữ
trong localStorage. Polygon OBB không được tô như mask. Kiểm tra bằng
`npm run test:overlay`.
