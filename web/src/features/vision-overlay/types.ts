/** Toạ độ xyxy, trước resize/letterbox của inference; cùng chiều với media gốc. */
export type BoundingBox = readonly [number, number, number, number];
export type Keypoint = {
  x: number;
  y: number;
  confidence?: number;
  visible?: boolean;
};
export type Detection = {
  id?: string | number;
  classId?: string | number;
  label?: string;
  confidence?: number;
  bbox?: BoundingBox;
  /** Giữ nguyên index; dùng null cho khớp không có dữ liệu. */
  keypoints?: readonly (Keypoint | null)[];
};
export type DetectionFrame = {
  frameId?: string | number;
  /** Kích thước ảnh/frame gốc, không phải kích thước tensor đã padding. */
  sourceSize: { width: number; height: number };
  coordinates?: "pixels" | "normalized";
  detections: readonly Detection[];
};
export type SkeletonEdge = readonly [number, number];
export type MediaFit = "contain" | "cover" | "fill";
export type OverlayOptions = {
  showBoxes?: boolean;
  showLabels?: boolean;
  showConfidence?: boolean;
  showKeypoints?: boolean;
  showSkeleton?: boolean;
  confidenceThreshold?: number;
  keypointThreshold?: number;
  skeleton?: readonly SkeletonEdge[];
  lineWidth?: number;
  pointRadius?: number;
  fontSize?: number;
  /** Nếu media bị lật ngang bằng CSS thì bật cờ này để overlay lật cùng. */
  mirrored?: boolean;
  /** object-position theo tỷ lệ; mặc định center. Phải khớp CSS của media. */
  position?: { x: number; y: number };
};

/** Skeleton COCO 17 keypoint, index 0-based; không tự áp cho model pose khác. */
export const COCO_POSE_SKELETON: readonly SkeletonEdge[] = [
  [15, 13],
  [13, 11],
  [16, 14],
  [14, 12],
  [11, 12],
  [5, 11],
  [6, 12],
  [5, 6],
  [5, 7],
  [6, 8],
  [7, 9],
  [8, 10],
  [1, 2],
  [0, 1],
  [0, 2],
  [1, 3],
  [2, 4],
  [3, 5],
  [4, 6],
];
