# Bộ đọc media của AI engine

Được đưa vào AI từ `media-sources/media_sources`, revision gốc
`0a743f22b239aaf705c948b7308aa7afc17f1597`, và chỉnh lại lifecycle, decoder,
metadata, logging cùng contract batch cho VisionKit. Runtime không phụ thuộc
thư mục clone ở root.

## Ranh giới trách nhiệm

- Reader: mở/đóng source, giải mã BGR `uint8`, stride và metadata gốc.
- Adapter Ultralytics: nạp model, suy luận, pacing video và serialize kết quả.
- Worker: kiểm checksum, giới hạn đường dẫn/protocol, timeout, huỷ process và log.
- Backend: upload, lưu file/DB, điều phối run và chuyển kết quả lên frontend.

Ảnh/video của API hiện tại đã dùng reader này. Image/video HTTP vẫn chỉ nhận
file trong storage đã xác minh. RTSP có endpoint nội bộ riêng `/api/v1/inference/stream`, chỉ backend gọi bằng source đã lưu;
frontend live chưa được nối. Webcam/YouTube vẫn chỉ có reader Python nội bộ.
Webcam id là thiết bị trên máy AI, không phải webcam của trình duyệt.

## Cách dùng

Một nguồn, không tạo thread nền:

```python
from app.media_sources import SourceType, create_media_source

with create_media_source(path, source_type=SourceType.VIDEO, vid_stride=2) as reader:
    for frame, meta in reader:
        result = model.predict(frame)
```

Ảnh dùng Pillow + pillow-heif, chỉnh EXIF trước khi chuyển RGB sang BGR. Hỗ trợ
PNG/JPEG/WebP/BMP/TIFF/GIF (frame đầu)/AVIF/HEIC/HEIF theo codec Pillow hiện có.
Kiểm tra giới hạn 64 triệu pixel trước load/convert. `ndarray` đầu vào được hiểu
là BGR; gray/BGRA được chuyển sang 3 kênh. Dtype khác `uint8` và ảnh rỗng bị từ chối.

Video dùng FFMPEG, áp dụng orientation metadata, `grab` mọi frame nhưng chỉ
`retrieve` mỗi N frame. `timestamp_ms` lấy PTS khi hợp lệ, fallback index/FPS.
Reader không sleep; adapter giữ pacing để preview hiện tại không thay đổi.
Số frame của container là ước lượng; EOF trước số frame khai báo được báo lỗi
thay vì âm thầm hoàn tất. FPS không hợp lệ và lỗi retrieve cũng là lỗi source.

Nhiều nguồn đồng nhất (tối đa 16):

```python
from app.media_sources import MediaSources

with MediaSources(["rtsp://camera-a/live", "rtsp://camera-b/live"]) as sources:
    for frames, metas in sources:
        results = model.predict(frames)
        for result, meta in zip(results, metas):
            consume(meta.source_index, result)
```

- `frames[i]` luôn tương ứng `metas[i]`; dùng **meta.source_index**, không dùng vị
  trí hiện tại trong batch, để nhận diện source gốc.
- File batch đọc tuần tự không dùng threadpool. Nguồn ngắn hết trước sẽ được đóng;
  vẫn đọc hết nguồn dài. Đây là thay đổi so với bản gốc dừng theo file ngắn nhất.
- Stream batch giữ một slot mới nhất/source. Trả ngay khi có ít nhất một nguồn
  mới, không chờ tất cả camera. Batch có thể chứa subset source, không đảm bảo các
  camera đồng bộ thời gian. Không tích lũy lịch sử frame.
- Exception từ một reader hoặc quá 15 giây không có frame sẽ dừng batch và báo
  `StreamError`. Một camera đang reconnect không cản camera khác trả frame mới.
- `timestamp` là Unix giây lúc đọc; `timestamp_ms` là vị trí file video và là
  `None` cho stream live. Đây không phải thời gian suy luận.

## Đóng và huỷ

Luôn dùng `with` hoặc gọi `close()`/`release()` trong `finally`. Đọc file và đóng
file trên cùng thread. Stream batch hỗ trợ `close()` từ thread điều khiển:

1. Set stop, đánh thức reconnect/consumer và bỏ tham chiếu slot/frame.
2. Thread đọc tự release capture trong `finally`; không release chéo khi đang read.
3. Chờ tổng cộng tối đa 2 giây. Nếu còn thread sống, **raise `StreamError` và giữ
   handle thread**, cấm mở lại cho đến khi thread cũ thực sự dừng.
4. Sau khi thread dừng, gọi `close()` lại để xác nhận dọn xong trước khi mở lại.

Không thể cưỡng chế dừng native webcam read từ Python thread. Worker process
là ranh giới huỷ cuối cùng cho AI engine. Iterator batch hết nguồn không tự mở
lại; phải vào context mới hoặc gọi `open()` tường minh.

## Nguồn mạng và dependency

RTSP/RTMP dùng FFMPEG có open/read timeout 5 giây, không fallback bỏ timeout.
Reconnect mặc định tối đa 5 lần, backoff có thể ngắt; `reconnect_forever=True`
phải chọn tường minh. Bản tích hợp bỏ nhánh GStreamer tự phát hiện codec của
bản clone để có một đường capture/timeout thống nhất. Webcam dùng backend mặc
định của OpenCV. OpenCV phải được build với backend tương ứng.

YouTube chỉ import `yt-dlp` khi mở nguồn:

```bash
uv sync --locked --extra youtube
```

Resolve một video, giới hạn socket/retry, không tải playlist; live dùng
latest-frame, VOD dùng tuần tự. Không trộn live và VOD cùng batch. Signed URL
hết hạn/mất kết nối chưa được tự resolve lại. RTSP đã có endpoint AI nội bộ riêng
(xem README AI); YouTube/webcam vẫn chưa được bật qua API inference của VisionKit.

Module chỉ dùng logger `app.media_sources`, không gọi `dictConfig`, không
cài handler khi import. Worker cấu hình log ra stderr, collector hiện tại thu
vào backend cùng run id. Nhãn URL trong log/metadata che credentials và query;
không gọi cấu hình logger màu từ repo gốc.

## Kiểm chứng

Từ `ai/`:

```bash
YOLO_AUTOINSTALL=false uv run python -m unittest discover -s tests -v
uv run ruff check app tests
uv run ruff format --check app tests
```

Test ảnh/video dùng codec thật. Test mạng dùng capture/resolver giả; test batch
chạy thread thật, kiểm close timeout, reopen, nguồn chậm, lỗi, weakref frame và
50 vòng mở/đóng không tăng thread. Kiểm thử adapter dùng Results Ultralytics
thật để kiểm màu BGR, EXIF, stride, pacing, JSON và cleanup khi model/consumer lỗi.
Không suy diễn test giả lập thành đã thử camera/RTSP/YouTube thực tế.
