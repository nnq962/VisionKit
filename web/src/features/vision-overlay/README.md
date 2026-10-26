# Vision overlay

Canvas bbox/keypoint dùng chung cho ảnh, video file hoặc webcam. Không phụ thuộc YOLO, backend, WebSocket hay inference. Canvas chỉ chứa annotation, không sao chép frame gốc và không chặn thao tác media.

## Dùng component

Trong Client Component:

```tsx
import { DetectionMedia, COCO_POSE_SKELETON, type DetectionFrame } from "@/features/vision-overlay";

const result: DetectionFrame = {
  frameId: 42,
  sourceSize: { width: 1920, height: 1080 },
  coordinates: "pixels",
  detections: [{
    classId: 0,
    label: "person",
    confidence: 0.94,
    bbox: [120, 80, 460, 920],
    keypoints: [{ x: 240, y: 130, confidence: 0.91 }, null],
  }],
};

<DetectionMedia kind="image" src={imageUrl} alt="Kết quả nhận diện" result={result} />

<DetectionMedia
  kind="video"
  src={videoUrl}
  label="Video nhận diện"
  result={latestResult}
  staleAfterMs={2000}
  options={{ skeleton: COCO_POSE_SKELETON, keypointThreshold: 0.3 }}
  videoProps={{ autoPlay: true, muted: true }}
/>
```

Mặc định wrapper `aspect-video`, media `object-fit: contain`, căn giữa. Dùng `className`/`style` để đặt kích thước wrapper, `fit="cover"` để crop hoặc `fit="fill"` để stretch. Resize, loaded metadata và DPR/zoom tự kích hoạt vẽ lại. `imageProps`/`videoProps` truyền các native event và thuộc tính media; với webcam, gán `event.currentTarget.srcObject` trong callback media phù hợp hoặc dùng hook trực tiếp. Hình ảnh gốc vẫn cần URL mà trình duyệt đọc được.

## Dùng hook với preview đang có

```tsx
const { mediaRef, canvasRef, canvasStyle, setResult, clear } = useDetectionOverlay({
  options: { skeleton: COCO_POSE_SKELETON },
  staleAfterMs: 2000,
});

// Trong callback dữ liệu đã parse/validate từ transport:
// setResult(frame);
// Khi ngắt kết nối/chuyển run/source:
// clear();

<div className="relative aspect-video overflow-hidden">
  <video ref={mediaRef} className="size-full object-contain" autoPlay muted playsInline />
  <canvas ref={canvasRef} style={canvasStyle} aria-hidden="true" />
</div>
```

Hook trả callback refs, gắn vào **chính media element** và canvas. Khi cần `srcObject`, callback ref có thể gọi `mediaRef(element)` rồi gán stream; callback nên ổn định bằng `useCallback`. Wrapper phải `position: relative`, canvas phủ cùng vùng preview. Đặt border/padding lên wrapper, không đặt lên media/canvas. Hook hỗ trợ CSS fit `contain`, `cover`, `fill`; mặc định object-position center. Nếu đổi object-position, truyền `options.position={ x:0, y:0 }` tương ứng góc trái trên (tỷ lệ 0–1). Khi media dùng `scaleX(-1)`, truyền `mirrored:true`; component tự lật media cho khớp. Không hỗ trợ rotation, skew hay transform tuỳ ý trên media.

Có thể dùng controlled `useDetectionOverlay({ result })` thay `setResult`. Cập nhật object result bất biến; tránh trộn hai cách điều khiển trong cùng một preview. `result=null`, `clear()` hoặc `detections:[]` xoá canvas. `redraw()` vẽ lại nếu bố cục ngoài hook thay đổi mà ResizeObserver không thấy.

## Hợp đồng toạ độ

- `sourceSize` là width/height frame **gốc hiển thị**, trước resize/padding inference. AI/adapter phải hoàn nguyên letterbox, xoay EXIF và các phép tiền xử lý trước khi gửi vào hook. Hook không tự suy ra phép tiền xử lý model.
- `bbox=[x1,y1,x2,y2]`, đơn vị pixel gốc; `coordinates:"normalized"` đổi toàn bộ bbox/keypoint sang 0–1. Gốc ở góc trái trên. Mỗi frame có thể đổi độ phân giải.
- `keypoints` giữ index gốc của model, có thể là `null`. `visible:false`, confidence thấp hoặc điểm ngoài frame sẽ không vẽ. `(0,0)` vẫn là điểm hợp lệ nếu visible/confidence cho phép.
- `skeleton` là mảng cặp index **0-based**, truyền theo schema model. Có sẵn `COCO_POSE_SKELETON` cho đúng thứ tự COCO 17. Mặc định chỉ vẽ điểm, không tự đoán skeleton.
- Confidence 0–1. Trường optional thiếu confidence vẫn được vẽ. `confidenceThreshold` lọc detection, `keypointThreshold` lọc từng khớp. Dữ liệu geometry không hữu hạn/bbox đảo chiều bị bỏ qua; transport vẫn cần kiểm tra JSON trước khi gọi hook.

## Vòng đời và hiệu năng

`setResult()` thay toàn bộ kết quả hiện tại. Các lần gọi trước cùng một animation frame chỉ vẽ kết quả cuối; không có hàng chờ frame hoặc loop vẽ liên tục. Resize/load/options thay đổi cũng vẽ lại. Màu ổn định theo class, nét/chữ giữ kích thước CSS pixel trên màn hình Retina. Label/đường nối được clip theo vùng media, không tràn vào letterbox.

`staleAfterMs=0` mặc định giữ kết quả cho ảnh tĩnh. Với live, đặt giá trị dương **ngay từ khi tạo preview** để xoá kết quả sau khoảng đó kể từ lần nhận mới nhất. Tự cleanup RAF, observers, listeners và timer khi unmount. Caller chịu trách nhiệm đóng WebSocket/dừng stream, xoá khi chuyển run/source và đồng bộ media/result nếu cần. Đây là lớp vẽ kết quả mới nhất, không buffer timeline, tracking hay chạy inference.

Đổi `src`/`kind` của component tạo lại media/canvas; caller đồng thời phải reset `result` để không truyền lại kết quả của source cũ. Canvas `aria-hidden`; bên dùng component nên cung cấp danh sách/text kết quả để screen reader đọc được.

## Kiểm tra

`npm run test:overlay` kiểm tra phép chiếu, letterbox, crop, resize và mirror bằng Node >=22.18 (TypeScript type stripping). Canvas/hook đã được kiểm tra thêm bằng pixel trên Chrome với DPR=2, cả ảnh và video.
