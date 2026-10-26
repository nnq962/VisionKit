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
- Các thư mục adapters/inference giữ chỗ cho các bước chạy AI sau.

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

Results normalize detections/pose keypoints into original image pixel coordinates for the reusable web canvas. Classification returns top5; segmentation/OBB additionally retain polygons. Pose points are rendered without assuming custom skeleton ordering. YOLOE models requiring text/visual prompts are not configured by this MVP. Video files use the streaming endpoint below; webcam/RTSP inference is not connected yet.

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
