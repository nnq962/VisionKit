# VisionKit

VisionKit project.

## Modules

- `web/`: Next.js web application.
- `backend/`: Python 3.10 backend, managed with uv.
- `ai/`: internal model inspection/inference service, managed with uv.

Runtime source metadata is stored in `data/visionkit.sqlite3` by `backend/app/db/` and `backend/app/modules/sources/`. Media files and database files under `data/` are local and ignored by Git.

## Local development

Start Docker Desktop (or Docker Engine + Compose), then install dependencies once:

```bash
docker compose pull mediamtx
(cd backend && uv sync)
(cd ai && uv sync)
(cd web && npm install)
```

From the project root (Linux/macOS, Python >=3.10):

```bash
./dev.py
```

The launcher starts MediaMTX, then AI, waits for its health API, then starts backend and checks
that its log collector can reach AI. Finally it starts the web development server
and verifies the frontend API proxy. It sets the internal URLs and CORS origins
for the selected ports automatically. No model is loaded until requested.

Preferred ports are frontend **3001**, backend **8000**, AI **8001**. If a preferred
port is occupied, the launcher chooses an unused port and prints the actual URL.
An explicitly requested port must be free; it never stops or takes over existing
services. Stop an earlier Next.js development session before starting another
against the same `web/` directory (Next.js permits only one dev server per checkout).

To use the ports from this working session:

```bash
./dev.py --web-port 3002 --backend-port 18000 --ai-port 18001
```

Stop the managed session from another terminal with `./dev.py --stop` (add the
same `--data-dir` if you started an isolated session). The launcher validates its
session lock/PID and does not stop manually started services. Duplicate launchers
against the same data directory are rejected before opening the database.

Keep the terminal open. **Ctrl+C** stops every process started by that invocation,
including Next.js children and AI workers. If a service exits unexpectedly, the
launcher reports the failure and shuts down its remaining services so backend is
not left running without AI. Other applications are unaffected.

Service stdout/stderr is saved in `data/dev-logs/{ai,backend,web}.log`, with up to
two rotated backups and a 5 MiB limit per file. The existing in-app runtime log
viewer remains available through backend; these launcher files are for startup
and process diagnostics. The launcher does not install dependencies or auto-reload
Python services; restart it after backend/AI code changes. Next.js retains HMR.

Useful test options:

```bash
# Separate database/files, without affecting your workspace data:
./dev.py --no-web --data-dir /tmp/visionkit-sandbox --backend-port 18100 --ai-port 18101

# Launcher port/readiness/signal/failure-cleanup regression tests:
python3 -m unittest discover -s tests -v
```

`--data-dir` overrides database, source, model and run paths for both Python
services. Without it, existing `VISIONKIT_*` storage settings keep working, with
`data/` in this repository as the default. The web calls backend via `/api/v1`.
API documentation is at the backend URL printed by the launcher, under `/docs`.

## RTSP preview via MediaMTX / WebRTC

Camera preview uses RTSP/TCP → MediaMTX → WebRTC → browser `<video>`. Python only
handles source configuration, camera status and WHEP SDP signaling. Preview has
no frame decoding, JPEG encoding, image transfer or transcoding. The browser hook
keeps the same peer connection / MediaStream across client-side route changes.

`./dev.py` runs MediaMTX in Docker Compose using the official `bluenviron/mediamtx:1.21.3`
image, pinned by registry digest in `compose.yaml`. AI/backend/web stay local.
Preferred relay host ports are Control API 9997, WHEP HTTP 8889, ICE UDP+TCP 8189
and RTSP 8554; occupied ports are skipped. Each data directory gets its own Compose
project. Ctrl+C / `./dev.py --stop` stops and removes only that project's relay
container/network; saved sources, models and database remain under `data/`.

The launcher requires a running Docker daemon. It downloads the pinned image if
missing. `--no-media` uses an externally managed relay at backend
`VISIONKIT_MEDIAMTX_API_URL` / `VISIONKIT_MEDIAMTX_WEBRTC_URL`.
To run MediaMTX independently: `docker compose up -d mediamtx`, then
`./dev.py --no-media`; stop it with `docker compose down`.
Do not run both managed and independent modes at once.

Docker publishes the relay ports only on host loopback for local development;
listeners bind inside the container. Configuration is mounted read-only and there
are no data volumes for the relay. Camera LAN URLs are unchanged. When started
by the launcher, camera localhost/127.0.0.1/::1 is translated to
`host.docker.internal` only in the internal MediaMTX payload; the saved URL stays
unchanged. An independently managed relay can enable this with backend
`VISIONKIT_MEDIAMTX_SOURCE_HOST=host.docker.internal`.
For remote browsers, deployment must configure reachable ICE hosts/listeners and
TURN if needed; proxying HTTP alone does not forward WebRTC media. The Control API
must stay internal. H.264 without B-frames is the practical camera configuration;
unsupported browser codecs produce an actionable error rather than a transcode.

Authentication feedback comes from MediaMTX source state: available/ready means
media can be read; RTSP 401/403 in `lastError` means camera rejected access. The
`online` flag alone does not prove readable media or successful authentication.
Anonymous cameras may also be readable. Saved credentials remain in the local
source DB and MediaMTX internal config; public session/status responses contain no
camera URL. The form also supports checking an unsaved RTSP URL and showing video
without adding it to the library. Its URL configuration lives only in backend RAM
and MediaMTX until the last viewing lease ends. Saving is a separate explicit action.

See `web/src/features/video-stream/README.md` for the hook and lifecycle contract.

Docker integration checks (isolated containers, no workspace data):

```bash
VISIONKIT_RUN_DOCKER_TESTS=1 python3 -m unittest discover -s tests -v
(cd backend && VISIONKIT_RUN_DOCKER_TESTS=1 .venv/bin/python -m unittest discover -s tests -v)
```

Live AI now runs alongside preview: check RTSP → select model → configure → Run.
AI reads the shared MediaMTX RTSP relay and returns JSON annotations while WebRTC
video remains independent. The default is at most 5 AI FPS for 60 minutes,
configurable in the pipeline. Runs continue across routes and can be stopped from
the Run step after returning with the same configuration. `VISIONKIT_MEDIAMTX_RTSP_URL`
configures the relay address reachable by AI (launcher sets it automatically).

Ordinary YouTube videos are also available in the source picker: paste a link →
prepare temporary video → preview/seek → select model → run AI. This uses a
bounded yt-dlp download (up to 720p H.264 MP4), not the RTSP relay. Cached video
is temporary and separate from the source library. YouTube Live is not enabled.
Backend setup now includes yt-dlp/EJS via `uv sync --locked`; Node.js must be on
PATH for YouTube extraction. See the backend/web READMEs for limits and lifecycle.

Webcam / USB now supports AI-host devices directly by OpenCV index (default 0).
The UI notes that browser and server should run on the same machine. Check takes
one snapshot and releases capture; Run opens the camera directly for YOLO, with
bounded HTTP frame preview and JSON annotations. No MediaMTX is used for webcam.

## Đếm hiện diện theo vùng

Sidebar Analytics có hai màn riêng:

- **Counting Configuration** (`/counting/configure`): tạo hoặc chọn cấu hình theo
  tên (ví dụ “Cấu hình 1”, “Cấu hình 2”), chọn source → model → class, thông số và
  polygon. **Lưu cấu hình** lưu tại chỗ, giữ nguyên editor/video và báo thành công;
  **Mở giám sát** chuyển sang Monitor. Nguồn đang chạy cần dừng trước khi sửa.
- **Counting Monitor** (`/counting/monitor`): chọn tên cấu hình đã lưu, xem số đếm theo
  vùng, video/RTSP, trạng thái AI và bật/tắt lớp hiển thị. **Bắt đầu giám sát /
  Chạy lại / Dừng AI** điều khiển run thật. **Cấu hình** mở màn thiết lập.

Hai màn có liên kết chuyển qua lại. `/counting` và `/counting/setup` chuyển đến
màn cấu hình. Chuyển trang không dừng AI. Video terminal hiển thị frame cuối;
RTSP không có dữ liệu mới hiển thị “—”. Bảng luôn hiển thị tất cả vùng và dòng
**Tổng cộng**, không loại trùng đối tượng giữa các vùng chồng nhau.

Backend lưu cấu hình trong bảng SQLite `counting_profiles`, mỗi cấu hình có tên
và ID riêng, lưu nguồn/model/class/polygon/thông số cùng ID lượt riêng. Có thể lưu
nhiều cấu hình cùng video mà không ghi đè nhau. Tên trùng không phân biệt hoa/thường
bị từ chối. Khi chạy, backend lấy snapshot theo ID cấu hình; chặn chạy trùng nguồn.
Migration tự chuyển cấu hình nguồn cũ thành “Cấu hình 1”, “Cấu hình 2”,… và giữ
con trỏ lượt cũ. Xoá/hết hạn run không xoá cấu hình đã lưu.

**Chạy liên tục** nối lượt RTSP và lặp video khi kết thúc, thử lại khi AI/camera
lỗi với backoff 2–60 giây. Worker đang chạy không gửi dữ liệu hơn 45 giây sẽ bị
thu hồi và kết nối lại. Monitor tự tìm lượt mới qua backend; các snapshot tự nối
cũ được dọn để không tăng dung lượng vô hạn. Việc chuyển lượt có khoảng ngắt ngắn.
RTSP vẫn dùng lượt hữu hạn 1–240 phút nhưng tổng thời gian dịch vụ không bị giới hạn.

**Tự chạy khi bật dịch vụ** chỉ dùng cùng Chạy liên tục: bật và lưu sẽ bắt đầu
ngay, sau đó khôi phục khi backend khởi động lại. **Dừng AI** hoặc **Dừng để chỉnh
sửa** tắt ý định chạy; trạng thái dừng được giữ qua restart cho đến khi bấm chạy
lại. Chạy liên tục không bật tự khởi động sẽ không tự tiếp tục sau restart.
Nguồn/model không hợp lệ được báo để chỉnh; không tạo lượt trùng trên cùng nguồn.
Supervisor hiện dùng một tiến trình backend (một Uvicorn worker).

Chạy dài hạn bằng `python3 dev.py --supervise` để launcher khởi động lại cả tiến
trình AI/backend/web/MediaMTX bị thoát với backoff. Chế độ dev thông thường vẫn
báo lỗi và dừng phiên khi có dịch vụ thoát. Launcher cần được khởi chạy lại sau
khi máy khởi động; tính năng này không tự cài dịch vụ hệ điều hành.

**Nhân bản** tạo tên riêng và không bật tự chạy cho bản sao. **Xoá** chỉ nhận cấu
hình đã dừng, đưa vào thùng rác; **Hoàn tác** khôi phục mà không tự chạy AI.
Tên trùng khi khôi phục trả lỗi để người dùng đổi tên cấu hình đang trùng.
Chuyển cấu hình/nguồn, theo liên kết, đóng hoặc tải lại trang có thay đổi chưa lưu
sẽ được nhắc trước. Nút **Lưu cấu hình** ở đầu trang dùng được từ mọi bước,
với trạng thái chưa lưu/đã lưu và thông báo Sonner sau khi lưu. Có thể bấm trực
tiếp từng bước đã đủ nguồn/model; thêm video dùng chung vùng kéo thả với YOLO
pipeline. Khi AI đang chạy vẫn có thể chuyển các bước hoặc chọn cấu
hình khác; vùng/thông số chỉ sửa được sau khi dừng nguồn đang đếm.

Hai màn dùng chung YOLOE `.pt`,
Model Hub, file/RTSP, MediaMTX, worker và cơ chế dừng. Bộ prompt y tế mặc định:
`person`, `wheelchair`, `hospital stretcher`, `hospital bed`, `medical trolley`,
`IV pole`; có thể tùy chỉnh class. Đây là số detection trong từng frame, chưa
tracking hoặc đếm lượt vào/ra.

Màn cấu hình gồm ba bước, với **Quay lại / Tiếp tục** để giữ lựa chọn:

1. **Chọn source**: chuyển giữa **Source mới / Đã lưu**, tìm/lọc video hoặc RTSP
   và xem thông tin nguồn ở bên cạnh. Nguồn mới cần lưu trước khi tiếp tục.
2. **Chọn model**: danh sách YOLOE .pt và thông tin model dùng chung với pipeline.
3. **Vùng và thông số**: tùy chỉnh **Class YOLOE** (mỗi dòng một class hoặc ngăn bằng
   dấu phẩy) rồi **Áp dụng class**. Tối đa 80 class, mỗi class 80 ký tự; lưu cùng nguồn,
   từng vùng chọn tập class riêng. Có thể dùng lại **Bộ class y tế**. Chọn khung hình, bấm **Vẽ vùng**, bấm từ 3–32 đỉnh rồi
   **Hoàn tất vùng**. Đặt tên/màu, chọn class và kéo đỉnh để sửa; chỉnh Confidence,
   IoU và thiết bị. **Lưu cấu hình** kiểm tra thông số và lưu vào cấu hình đang chọn.

Màn giám sát tách riêng Bounding box, tên class/confidence, segmentation và điểm
đếm. Số liệu cập nhật qua WebSocket; tải lại trang khôi phục lượt đang chạy.

Điểm đếm là giữa cạnh dưới bbox, được đánh dấu chấm trắng trên video. Điểm trên
biên thuộc vùng; các vùng chồng nhau đếm độc lập. Polygon dùng toạ độ 0–1 để resize
và letterbox không làm lệch; tối đa 20 vùng mỗi nguồn. Backend từ chối vùng tự cắt,
trùng đỉnh hoặc không có diện tích. Đổi tỷ lệ ảnh sẽ làm cấu hình đếm mất hiệu lực;
đổi góc camera/crop cần người dùng vẽ lại vùng.

Backend tính số đếm cho từng frame trước khi lưu/phát snapshot qua API runs.
Frontend nhận bbox, số đếm và tiến độ qua WebSocket `/api/v1/runs/{id}/events`,
kèm HTTP polling dự phòng khoảng 1 giây như YOLO pipeline. Video
phát liên tục với bbox mới nhất, đặt vị trí lúc bắt đầu và dừng tại frame
AI cuối; RTSP vẫn dùng WebRTC preview độc lập nên có thể
trễ nhẹ so với detection. Mất kết quả live mới quá 3 giây hiển thị không khả dụng,
không biến thành 0. Mất preview riêng không dừng việc đếm nếu AI vẫn có dữ liệu.
Reload/chuyển trang tìm run theo nguồn từ backend, dự phòng bằng ID trong trình duyệt; inference
vẫn chạy ở backend. Chỉ giữ snapshot mới nhất, chưa có lịch sử/thống kê/tracking.
Giới hạn hiện tại vẫn là một worker inference đồng thời cho toàn bộ AI service.

Kiểm tra: `(cd backend && uv run python -m unittest discover -s tests -q)` và
`(cd web && npm run test:counting)`. Logic mới ở `backend/app/modules/counting/` và
`web/src/features/zone-counting/`; không cần thay đổi module AI; migration DB chạy tự động khi backend khởi động.
