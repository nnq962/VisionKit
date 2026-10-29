import { projectPoint, type MediaTransform } from "./geometry.ts";
import type {
  Detection,
  DetectionFrame,
  Keypoint,
  OverlayOptions,
} from "./types";

const PALETTE = [
  "#22d3ee",
  "#a3e635",
  "#fbbf24",
  "#fb7185",
  "#c4b5fd",
  "#2dd4bf",
];

/** Màu ổn định theo class; không đổi màu khi thứ tự detections thay đổi. */
export function detectionColor(detection: Detection): string {
  const key = String(detection.classId ?? detection.label ?? detection.id ?? 0);
  let hash = 0;
  for (let index = 0; index < key.length; index++)
    hash = (hash * 31 + key.charCodeAt(index)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

function positive(value: number | undefined, fallback: number, max: number) {
  return value !== undefined && Number.isFinite(value) && value > 0
    ? Math.min(value, max)
    : fallback;
}

/** Vẽ annotation trên context theo CSS pixel; caller phụ trách clear và scale DPR. */
export function drawDetections(
  ctx: CanvasRenderingContext2D,
  frame: DetectionFrame,
  transform: MediaTransform,
  options: OverlayOptions = {},
) {
  if (
    !frame.sourceSize ||
    ![frame.sourceSize.width, frame.sourceSize.height].every(
      (value) => Number.isFinite(value) && value > 0,
    ) ||
    !Array.isArray(frame.detections)
  )
    return;
  const normalized = frame.coordinates === "normalized";
  const threshold = options.confidenceThreshold ?? 0;
  const keypointThreshold = options.keypointThreshold ?? 0.25;
  const fontSize = positive(options.fontSize, 12, 40);
  const project = (x: number, y: number) =>
    projectPoint(
      x,
      y,
      frame.sourceSize,
      transform,
      normalized,
      options.mirrored,
    );
  const validKeypoint = (point: Keypoint | null) =>
    Boolean(
      point &&
      point.visible !== false &&
      Number.isFinite(point.x) &&
      Number.isFinite(point.y) &&
      point.x >= 0 &&
      point.y >= 0 &&
      point.x <= (normalized ? 1 : frame.sourceSize.width) &&
      point.y <= (normalized ? 1 : frame.sourceSize.height) &&
      (point.confidence === undefined ||
        (Number.isFinite(point.confidence) &&
          point.confidence >= keypointThreshold)),
    );
  ctx.save();
  ctx.beginPath();
  ctx.rect(
    transform.clip.x,
    transform.clip.y,
    transform.clip.width,
    transform.clip.height,
  );
  ctx.clip();
  ctx.lineWidth = positive(options.lineWidth, 2, 12);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.font = `600 ${fontSize}px Manrope, sans-serif`;
  // Tô mọi mask trước bbox/nhãn để mask phía sau không che annotation đã vẽ.
  if (options.showSegments === true) {
    for (const detection of frame.detections) {
      const polygon = detection?.polygon;
      if (
        !Array.isArray(polygon) || polygon.length < 3 ||
        (detection.confidence !== undefined &&
          (!Number.isFinite(detection.confidence) || detection.confidence < threshold)) ||
        polygon.some((point) => !Array.isArray(point) || point.length !== 2 || !point.every(Number.isFinite))
      ) continue;
      const points = polygon.map(([x, y]) => project(x, y));
      if (points.some((point) => !point)) continue;
      ctx.save();
      ctx.strokeStyle = detectionColor(detection);
      ctx.fillStyle = detectionColor(detection);
      ctx.beginPath();
      ctx.moveTo(points[0]!.x, points[0]!.y);
      for (const point of points.slice(1)) ctx.lineTo(point!.x, point!.y);
      ctx.closePath();
      ctx.globalAlpha = 0.25;
      ctx.fill();
      ctx.globalAlpha = 0.85;
      ctx.stroke();
      ctx.restore();
    }
  }
  for (const detection of frame.detections) {
    if (
      !detection ||
      (detection.confidence !== undefined &&
        (!Number.isFinite(detection.confidence) ||
          detection.confidence < threshold))
    )
      continue;
    const color = detectionColor(detection);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    const bbox = detection.bbox;
    if (
      bbox?.length === 4 &&
      bbox.every(Number.isFinite) &&
      bbox[2] > bbox[0] &&
      bbox[3] > bbox[1]
    ) {
      const maxX = normalized ? 1 : frame.sourceSize.width,
        maxY = normalized ? 1 : frame.sourceSize.height;
      const a = project(Math.max(0, bbox[0]), Math.max(0, bbox[1]));
      const b = project(Math.min(maxX, bbox[2]), Math.min(maxY, bbox[3]));
      if (
        a &&
        b &&
        Math.min(maxX, bbox[2]) > Math.max(0, bbox[0]) &&
        Math.min(maxY, bbox[3]) > Math.max(0, bbox[1])
      ) {
        const x = Math.min(a.x, b.x),
          y = Math.min(a.y, b.y),
          w = Math.abs(b.x - a.x),
          h = Math.abs(b.y - a.y);
        if (options.showBoxes !== false) ctx.strokeRect(x, y, w, h);
        if (options.showLabels !== false) {
          const label = (
            detection.label ??
            (detection.classId !== undefined ? String(detection.classId) : "")
          ).slice(0, 120);
          const score =
            options.showConfidence !== false &&
            detection.confidence !== undefined
              ? `${Math.round(Math.max(0, Math.min(1, detection.confidence)) * 100)}%`
              : "";
          const text = [label, score].filter(Boolean).join(" · ");
          if (text) {
            const width = Math.min(
              ctx.measureText(text).width + 12,
              transform.clip.width,
            );
            const height = fontSize + 10;
            const labelX = Math.max(
              transform.clip.x,
              Math.min(x, transform.clip.x + transform.clip.width - width),
            );
            const labelY = Math.max(
              transform.clip.y,
              Math.min(
                y - height,
                transform.clip.y + transform.clip.height - height,
              ),
            );
            ctx.save();
            ctx.beginPath();
            ctx.rect(labelX, labelY, width, height);
            ctx.clip();
            ctx.fillStyle = color;
            ctx.fillRect(labelX, labelY, width, height);
            ctx.fillStyle = "#0f172a";
            ctx.textBaseline = "middle";
            ctx.fillText(text, labelX + 6, labelY + height / 2);
            ctx.restore();
          }
        }
      }
    }
    const points = detection.keypoints ?? [];
    if (options.showSkeleton !== false) {
      for (const [start, end] of options.skeleton ?? []) {
        if (
          !Number.isInteger(start) ||
          !Number.isInteger(end) ||
          start < 0 ||
          end < 0 ||
          !validKeypoint(points[start] ?? null) ||
          !validKeypoint(points[end] ?? null)
        )
          continue;
        const a = project(points[start]!.x, points[start]!.y),
          b = project(points[end]!.x, points[end]!.y);
        if (a && b) {
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
    }
    if (options.showKeypoints !== false) {
      for (const point of points) {
        if (!validKeypoint(point)) continue;
        const projected = project(point!.x, point!.y);
        if (!projected) continue;
        ctx.beginPath();
        ctx.arc(
          projected.x,
          projected.y,
          positive(options.pointRadius, 3, 20),
          0,
          Math.PI * 2,
        );
        ctx.fillStyle = color;
        ctx.fill();
      }
    }
  }
  ctx.restore();
}
