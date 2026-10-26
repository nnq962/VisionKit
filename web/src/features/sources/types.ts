export type SourceKind =
  "image" | "video" | "stream" | "youtube" | "webcam" | "screen";

export type VisionSource = {
  id: string;
  kind: SourceKind;
  name: string;
  location: string;
  status: "loading" | "ready" | "pending" | "error";
  file?: File;
  mediaStream?: MediaStream;
  deviceId?: string;
  previewUrl?: string;
  thumbnailUrl?: string;
  previewBlob?: Blob;
  width?: number;
  height?: number;
  duration?: number;
  size?: number;
  format?: string;
  fps?: number;
  error?: string;
  saved?: boolean;
  createdAt?: string;
  updatedAt?: string;
  originalFilename?: string;
  mimeType?: string;
  sha256?: string;
  previewLocation?: string;
  previewSize?: number;
};

export const sourceKinds: { value: SourceKind; label: string; hint: string }[] =
  [
    {
      value: "image",
      label: "Ảnh",
      hint: "JPG, PNG, WebP, HEIC/HEIF · một ảnh mỗi lần",
    },
    {
      value: "video",
      label: "Video",
      hint: "MP4, WebM, MOV · tuỳ codec trình duyệt hỗ trợ",
    },
    {
      value: "stream",
      label: "Camera / stream",
      hint: "Camera IP qua RTSP, RTMP hoặc HTTP(S)",
    },
    { value: "youtube", label: "YouTube", hint: "Đường dẫn video YouTube" },
    {
      value: "webcam",
      label: "Webcam / USB",
      hint: "Mở webcam hoặc camera USB ngay trên trình duyệt",
    },
    {
      value: "screen",
      label: "Chụp màn hình",
      hint: "Chọn màn hình, cửa sổ hoặc tab để chụp một ảnh",
    },
  ];

export const sourceLabel = (kind: SourceKind) =>
  sourceKinds.find((item) => item.value === kind)!.label;
