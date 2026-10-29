# VisionKit AI

Python 3.10 / uv. Service AI nội bộ, độc lập với backend quản lý dữ liệu.

## Chạy development

Từ `ai/`:

```bash
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Backend chạy port 8000, web port 3001. Backend gọi AI qua HTTP; cả hai đọc cùng thư mục model mặc định `data/models/` ở gốc monorepo. AI chỉ đọc file, không truy cập SQLite. Có thể đổi bằng `VISIONKIT_MODELS_PATH` ở **cả hai service**, trỏ tới cùng thư mục. Đường dẫn tương đối được tính từ thư mục chạy lệnh.

API nội bộ: `GET /api/v1/health`, `POST /api/v1/models/inspect` với JSON `{ "location": "<uuid>.pt", "sha256": "<64 ký tự hex>" }`. Không công khai service AI ra Internet; chỉ backend gọi địa chỉ loopback. Nếu triển khai trên hai máy/container, cần mount chung model storage và cấu hình URL/mạng nội bộ phù hợp.

## Metadata

- `.pt`: restricted loader của Ultralytics/PyTorch đọc checkpoint, không chạy forward/inference. Trích xuất họ model, tác vụ, tên class, số class, kích thước ảnh, stride, kiến trúc, scale, số tham số và phiên bản nếu checkpoint có lưu.
- `.onnx`: đọc graph/input shape và metadata nhúng, không cần ONNX Runtime; không nạp external weights. Graph thiếu thông tin family/task trả `needs_input` để khai báo bổ sung.
- Không suy đoán họ model hoặc tác vụ từ tên file. File hỏng/không hỗ trợ trả `failed`. Có metadata không đồng nghĩa đã chạy inference thành công.

Mỗi lượt inspect chạy trong subprocess, giới hạn một lượt cùng lúc, timeout 90 giây và kiểm tra SHA-256. Loader yêu cầu PyTorch >=2.6 và Ultralytics có `_SafeLoad`; không fallback sang pickle không hạn chế. Checkpoint chứa class tuỳ biến ngoài danh sách hỗ trợ có thể bị từ chối. Subprocess không phải sandbox hệ điều hành; MVP dành cho model đáng tin cậy trong môi trường local.

## Cấu trúc chính

- `app/main.py`: FastAPI nội bộ.
- `app/contracts/model.py`: hợp đồng request/metadata.
- `app/inspection/service.py`: kiểm soát đường dẫn, subprocess và timeout.
- `app/inspection/worker.py`: kiểm tra checksum, chọn bộ đọc định dạng.
- `app/inspection/pt.py`, `onnx.py`: trích xuất metadata theo định dạng.
- `app/media_sources/`: reader độc lập model cho ảnh/video và nguồn live.
- `app/adapters/ultralytics/`, `app/inference/`: suy luận và quản lý worker.

## Kiểm tra

```bash
uv run python -m unittest discover -s tests -v
uv run ruff check app tests
uv run ruff format --check app tests
```

Metadata phân biệt `family` (YOLO/YOLOE), `model_series` (YOLO26/YOLO11/YOLOv8/YOLOE-26…), `scale` (n/s/m/l/x) và `ultralytics_version` (phiên bản thư viện lưu/export model). Dòng model được đọc từ `model.yaml.yaml_file` nhúng trong PT hoặc định danh/mô tả ONNX nhúng; `series_source` ghi nguồn bằng chứng. Không dùng tên file upload hoặc phiên bản thư viện để đoán dòng. Thiếu/mâu thuẫn định danh trả null. Đây là metadata file khai báo, không phải chứng minh kiến trúc qua inference. Model đã inspect trước bản cập nhật cần **Đọc lại** để bổ sung các trường mới; không cần migration DB.

## Image inference

`POST /api/v1/inference/image` is internal to backend: relative model/source locations, SHA-256 for both, family/task and allowlisted options. Files must be under the configured shared model/run roots; absolute paths, symlinks and escapes are rejected. Each request runs a separate worker (cold model load), serialised within AI with a 180-second worker timeout. Disconnect/cancellation kills the worker; there is no model cache yet.

Ultralytics handles `.pt` and ONNX; pinned `onnxruntime<1.24` retains Python 3.10 wheel support. HEIC/HEIF uses pillow-heif; input decoding applies EXIF orientation before inference. PT uses the restricted loader with no unsafe fallback or auto-install/download. ONNX external tensors and fixed batch other than 1 are rejected. Auto chooses CUDA/MPS/CPU for PT; ONNX currently runs CPU. Explicit unavailable devices return an actionable error rather than silently falling back. The subprocess is not an OS sandbox; keep this local service for trusted model artifacts.

Results normalize detections/pose keypoints into original image pixel coordinates for the reusable web canvas. Classification returns top5; segmentation/OBB additionally retain polygons. Pose points are rendered without assuming custom skeleton ordering. YOLOE text prompts are supported for unfused text/visual PT checkpoints; visual prompting is not yet available. Video files use the file streaming endpoint below; RTSP inference uses its separate internal stream endpoint. Local webcam inference is available through the dedicated webcam endpoint below.

## Video file inference

`POST /api/v1/inference/video` accepts the same request contract plus `options.vid_stride` (1–120), and streams `application/x-ndjson`: `frame`, `completed` or `error` events. Each frame includes original-coordinate detections, frameId/timestampMs and progress (processed count, source frame index, estimated total, source FPS, effective processing FPS, percent). Empty detections are emitted too. The worker loads the model once, uses local OpenCV/FFmpeg capture, applies rotation metadata to match browser display, and restricts protocols to file/pipe. It processes every Nth source frame, pacing at no faster than source time; slower hardware can lag the browser preview. It sends JSON only, never annotated video frames.

Image and video workers share one AI inference semaphore. Video supports the existing PT/ONNX adapters and device rules. The default input cap is 200 MiB via `VISIONKIT_MAX_VIDEO_UPLOAD_MB` (set consistently with backend); an event is capped at 8 MiB, idle timeout is 180 seconds, overall video run cap is four hours. Cancelling the HTTP stream or closing the generator kills the worker and releases capture/semaphore. No frame history, tracking or reconnect/resume within an interrupted video run.

## Runtime logs

`GET /api/v1/logs` is an internal, read-only endpoint for the backend collector.
It accepts `after`, `limit` (1–500, default 200), `min_level` (default INFO) and
optional UUID `run_id`. It returns `items`, `next_cursor`, `has_more`, `reset` and
`dropped`. See the complete web-facing contract in
[`../backend/README.md`](../backend/README.md#centralized-runtime-logs).

App/Uvicorn logs and worker stderr are retained in a 2,000-entry RAM ring per
process. Restart loses history; run one Uvicorn worker. Stderr is drained alongside
stdout without mixing log text into JSON/NDJSON. Worker messages are INFO,
structured image/video/inspection failures are ERROR. Caught worker exceptions
include a bounded traceback in the structured worker response; the API records it
on the ERROR entry independently of stderr throttling, then removes it from public
inference responses. Unexpected exceptions also write tracebacks to stderr.
Stderr floods are bounded and summarized. Image/inspection stdout is limited to
8 MiB; video is limited to 8 MiB per event. Overflow, timeout and cancellation
kill/reap workers and drain remaining pipes without accumulating discarded output.

`X-VisionKit-Run-ID` (UUID) propagates inference correlation from backend into AI
tasks and worker stderr capture without changing model request payloads. The
logging path never waits for a browser viewer. Log polling and health checks do
not produce log entries in the buffer.

## Bộ đọc source

Ảnh/video inference đã dùng [`app/media_sources`](app/media_sources/README.md).
Module trả frame BGR và metadata; Ultralytics chỉ nhận frame để suy luận.
Pillow giữ hỗ trợ HEIC/HEIF/EXIF; video giữ stride, rotation và pacing hiện tại.
RTSP/RTSPS inference dùng endpoint nội bộ riêng ở phần dưới. Các reader mạng
khác chưa được mở qua HTTP. Reader AI phục vụ suy luận, độc lập với preview
MediaMTX/WebRTC; không xoá decoder AI khi thay đổi cách phát video trên web.
YouTube là extra tùy chọn, không bắt buộc để chạy ảnh/video.

## Inference RTSP nội bộ

`POST /api/v1/inference/stream` nhận model location/checksum, family/task/options,
`stream_url` RTSP/RTSPS và `duration_seconds` (1–14400, default 3600). Đây là
endpoint riêng; image/video local vẫn giữ hợp đồng và protocol file/pipe cũ.
Backend chỉ đưa URL từ source đã lưu, không công khai endpoint AI cho trình duyệt.

Worker `app.inference.stream_worker` kiểm SHA-256 model rồi đưa URL qua stdin,
không qua command line. FFmpeg dùng RTSP/TCP, whitelist `rtsp,rtsps,tcp,tls,crypto`;
không mở file/HTTP source qua endpoint này. Không cần GStreamer. Worker dùng
`StreamBatchReader` latest-frame, tối đa một slot/source, cùng model/semaphore
hiện có, và chỉ gửi NDJSON metadata/detections, không gửi ảnh nhị phân.

Live `vid_stride` là khoảng index tối thiểu giữa hai frame chọn suy luận; index
có thể nhảy do latest-frame, không yêu cầu chia hết stride. Read timeout 3 giây,
open timeout 5 giây, batch no-frame timeout 15 giây. Reconnect có backoff và tối
đa 5 lần; batch no-frame timeout có thể kết thúc sớm hơn khi không nhận frame.
Đóng batch chờ tối đa 6 giây để reader tự nhả capture; vượt hạn là lỗi, worker
process vẫn được kill/reap. Huỷ HTTP cũng kill worker và nhả semaphore.

Event `frame` giữ JSON result hiện có; `progress.is_live=true`, `percent` và
`total_frames` là null; source FPS có thể null. `timestampMs` là thời điểm thu
frame tính từ khi bắt đầu đọc live, không phải PTS file video. Đến duration trả
`completed` cùng `reason="duration_limit"`; mất kết nối/EOF không được completed.
Service giới hạn tổng worker lifetime ở duration + 180 giây để dành cold load,
idle pipe tối đa 180 giây. Không cache model và không tự restart live worker.

RTSP native FFmpeg stderr có thể in URL nguyên văn; worker tắt output native
này và giữ Python logger qua stderr riêng. Lỗi stream trả thông báo chung,
không kèm traceback có thể chứa URL. Log reader vẫn vào collector hiện tại theo
run id. Validation không phản chiếu raw request; URL SecretStr chỉ được bỏ mask
khi ghi vào stdin worker. Bản ghi source trên backend còn lưu URL gốc trong DB
local, còn run record/public response không lưu URL bí mật.

`tests/inference/test_stream.py` kiểm contract/redaction, live stride/duration,
consumer failure, worker cancel/EOF/reap, path validation và checksum entrypoint.
Đã smoke test luồng HTTP + RTSP loopback H264/TCP với model thật CPU/CUDA;
chưa kiểm camera vật lý, RTSPS/TLS và network soak dài hạn.

Web live runs supply the MediaMTX relay URL to this stream endpoint, sharing the
camera connection with WebRTC preview. `options.max_fps` (1–60, default 5) paces
prediction, reading the newest slot after each wait. Capture continues replacing
old frames while the model runs; no inference backlog is accumulated. Video
frames are decoded only inside AI; backend receives JSON results.

## Local webcam

POST /api/v1/webcams/check probes a strict integer device_index (0–15, default 0)
in a separate worker with a 20-second timeout, returning dimensions and a single
JPEG before releasing capture. An active inference semaphore prevents probing
while a model is running. POST /api/v1/inference/webcam accepts the shared model
contract plus device_index/duration_seconds and runs the existing latest-frame
adapter with WebcamReader directly. There is no MediaMTX/browser upload.

The model loads once, reads newest frames and follows max_fps/duration settings.
Only webcam events include preview_jpeg, resized at most 960px/quality 70, for
backend HTTP preview. Detections remain in original-frame coordinates. Capture
and inference use the same frame; backend strips images from JSON/DB/WebSocket.
Cancel/timeout/worker termination releases the webcam. Device 0 is on the machine
running AI; OS camera permission must be granted to its Python/launcher process.

Webcam checks and webcam inference request a one-second capture warmup, dropping
initial frames before using a snapshot/result. Warmup is bounded and releases
capture on failure; other reader consumers keep the previous zero-warmup default.

## YOLOE text prompt

Chọn model YOLOE `.pt` trong pipeline chung. Bước Thông số có 22 vật thể gợi ý
bằng tiếng Việt và ô sửa prompt tiếng Anh (phân cách bằng dấu phẩy/xuống dòng).
Ví dụ: `person, car, motorcycle, laptop, computer monitor, cell phone`.
Run lưu `options.text_prompts` theo thứ tự; class ID và nhãn kết quả dựa trên
prompt của run, không dựa trên class metadata cũ. Không kết hợp với `classes`.
Giới hạn 1–80 prompt, mỗi prompt 1–80 ký tự, không trùng (không phân biệt hoa thường).

Chuẩn bị môi trường một lần, trước khi chạy (có Internet):

```bash
cd ai
uv sync --locked
uv run python -m app.inference.setup_yoloe --series all
```

`26` dùng `mobileclip2_b.ts`, `11` (cũng dùng cho YOLOE-v8) dùng `mobileclip_blt.ts`.
Mặc định setup chỉ tải `--series 26`; `all` chuẩn bị cả hai. Encoder nằm trong
`data/yoloe/`, hoặc `VISIONKIT_YOLOE_ENCODERS_PATH`; không vào thư viện weights/DB.
Tokenizer CLIP được ghim commit trong uv.lock. Inference chỉ nạp encoder local,
không tự cài dependency/tải encoder. Thiếu asset trả lỗi hướng dẫn setup.
Model/encoder chạy cùng thiết bị; mỗi worker tạo embedding một lần rồi nhả encoder
trước khi xử lý ảnh hoặc vòng lặp video/RTSP/webcam. Đổi prompt phải tạo run mới;
không thay đổi checkpoint hay metadata trên đĩa. Không có embedding cache xuyên run.
ONNX, prompt-free hoặc checkpoint đã fuse không hỗ trợ đổi text prompt.
