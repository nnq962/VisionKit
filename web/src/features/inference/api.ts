import type { DetectionFrame } from "@/features/vision-overlay";
import type { VisionSource } from "@/features/sources/types";
import type { YoloParameters } from "@/features/pipelines/yolo/types";

export type InferenceResult = DetectionFrame & {
  classifications: { classId: number; label: string; confidence: number }[];
  device: string;
  elapsedMs: number;
  speed: Record<string, number>;
  timestampMs?: number;
};
export type InferenceRun = {
  id: string;
  model_id: string;
  source_kind?: "image" | "screen" | "video" | "stream" | "webcam";
  progress?: {
    frames_processed: number;
    frame_index: number;
    total_frames: number | null;
    timestamp_ms: number;
    source_fps: number | null;
    is_live?: boolean;
    elapsed_seconds?: number;
    processing_fps: number;
    percent: number | null;
  } | null;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  result: InferenceResult | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};
const base = "/api/v1/runs";
async function request(
  path: string,
  options?: RequestInit,
): Promise<InferenceRun> {
  const response = await fetch(base + path, { cache: "no-store", ...options });
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Không thực hiện được lượt chạy.",
    );
  return body;
}
export async function startRun(
  source: VisionSource,
  modelId: string,
  parameters: YoloParameters,
  signal: AbortSignal,
) {
  if (!["image", "screen", "video", "stream", "youtube", "webcam"].includes(source.kind))
    throw new Error("Hiện hỗ trợ ảnh, ảnh màn hình, video file và RTSP.");
  const dimensions = parameters.imageSize.split("x").map(Number);
  if (source.kind === "webcam") {
    if (source.status !== "ready" || source.deviceIndex === undefined) throw new Error("Kiểm tra webcam máy AI trước khi chạy.");
    return request("/webcam", { method: "POST", headers: { "Content-Type": "application/json" }, signal,
      body: JSON.stringify({ model_id: modelId, device_index: source.deviceIndex, duration_seconds: Number(parameters.liveMinutes) * 60,
        options: { conf: Number(parameters.confidence), iou: Number(parameters.iou), imgsz: [dimensions[0], dimensions[1] ?? dimensions[0]], device: parameters.device, classes: parameters.classMode === "all" ? null : parameters.classes.map(Number), max_det: Number(parameters.maxDet), agnostic_nms: parameters.agnosticNms, vid_stride: Number(parameters.vidStride), max_fps: Number(parameters.liveFps) },
      }),
    });
  }
  if (source.kind === "youtube") {
    if (!source.youtubeSession || source.status !== "ready") throw new Error("Chuẩn bị video YouTube trước khi chạy AI.");
    return request("/youtube", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal,
      body: JSON.stringify({ model_id: modelId, session_id: source.youtubeSession, options: {
        conf: Number(parameters.confidence), iou: Number(parameters.iou),
        imgsz: [dimensions[0], dimensions[1] ?? dimensions[0]], device: parameters.device,
        classes: parameters.classMode === "all" ? null : parameters.classes.map(Number),
        max_det: Number(parameters.maxDet), agnostic_nms: parameters.agnosticNms,
        vid_stride: Number(parameters.vidStride),
      }}),
    });
  }
  if (source.kind === "stream") {
    if (!source.saved && !source.streamPreview) throw new Error("Kiểm tra RTSP trước khi chạy AI.");
    return request("/live", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal,
      body: JSON.stringify({
        model_id: modelId,
        ...(source.saved ? { source_id: source.id } : { preview_id: source.id }),
        duration_seconds: Number(parameters.liveMinutes) * 60,
        options: {
          conf: Number(parameters.confidence), iou: Number(parameters.iou),
          imgsz: [dimensions[0], dimensions[1] ?? dimensions[0]], device: parameters.device,
          classes: parameters.classMode === "all" ? null : parameters.classes.map(Number),
          max_det: Number(parameters.maxDet), agnostic_nms: parameters.agnosticNms,
          vid_stride: Number(parameters.vidStride), max_fps: Number(parameters.liveFps),
        },
      }),
    });
  }
  const body = new FormData();
  body.set("model_id", modelId);
  body.set("kind", source.kind);
  body.set(
    "options",
    JSON.stringify({
      conf: Number(parameters.confidence),
      iou: Number(parameters.iou),
      imgsz: [dimensions[0], dimensions[1] ?? dimensions[0]],
      device: parameters.device,
      classes:
        parameters.classMode === "all" ? null : parameters.classes.map(Number),
      max_det: Number(parameters.maxDet),
      agnostic_nms: parameters.agnosticNms,
      vid_stride: source.kind === "video" ? Number(parameters.vidStride) : 1,
    }),
  );
  if (source.saved) body.set("source_id", source.id);
  else if (source.file) body.set("file", source.file);
  else throw new Error("Tệp gốc không còn. Hãy chọn lại source.");
  return request("", { method: "POST", body, signal });
}
export const getRun = (id: string, signal?: AbortSignal) =>
  request(`/${encodeURIComponent(id)}`, { signal });
export const cancelRun = (id: string) =>
  request(`/${encodeURIComponent(id)}`, { method: "DELETE" });
export const runPreview = (id: string) =>
  `${base}/${encodeURIComponent(id)}/preview`;
export function eventsUrl(id: string) {
  const url = new URL(
    `${base}/${encodeURIComponent(id)}/events`,
    window.location.href,
  );
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export async function finishRun(id: string) {
  const response = await fetch(`${base}/${encodeURIComponent(id)}/resources`, { method: "DELETE" });
  if (!response.ok) throw new Error("Chưa dọn được tài nguyên lượt chạy. Bấm Hoàn thành để thử lại.");
}
