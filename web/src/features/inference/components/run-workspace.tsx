"use client";
import { DownloadIcon, PlayIcon, SquareIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { OverlayControls } from "./overlay-controls";
import { useOverlayPreferences } from "../use-overlay-preferences";
import { COCO_POSE_SKELETON, DetectionMedia } from "@/features/vision-overlay";
import type { VisionSource } from "@/features/sources/types";
import type { StoredModel } from "@/features/models/api";
import type { YoloParameters } from "@/features/pipelines/yolo/types";
import { useInferenceRun } from "../use-inference-run";
import { VideoRunPreview } from "./video-run-preview";
import { runPreview } from "../api";
import { LiveRunPreview } from "./live-run-preview";
import { RunMetrics } from "./run-metrics";

function RunWorkspaceContent({
  source,
  model,
  parameters,
}: {
  source: VisionSource | null;
  model: StoredModel | null;
  parameters: YoloParameters;
}) {
  const inference = useInferenceRun(source, model?.id ?? null, parameters);
  const { run } = inference;
  const { preferences, update: updateOverlay } = useOverlayPreferences();
  const supported = Boolean(
    source && ["image", "screen", "video", "stream"].includes(source.kind),
  );
  const video = source?.kind === "video";
  const live = source?.kind === "stream";
  const temporal = video || live;
  const result = temporal
    ? (run?.result ?? null)
    : run?.status === "completed"
      ? run.result
      : null;
  const pose =
    model?.task === "pose" ||
    Boolean(result?.detections.some((item) => item.keypoints?.length));
  const canConnect =
    pose &&
    !result?.detections.some(
      (item) => item.keypoints?.length && item.keypoints.length !== 17,
    );
  const overlayOptions = {
    showBoxes: preferences.boxes,
    showLabels: preferences.boxes && preferences.labels,
    showKeypoints: preferences.keypoints,
    showSkeleton: preferences.skeleton,
    skeleton: canConnect ? COCO_POSE_SKELETON : [],
  };
  const src = live ? undefined : run ? runPreview(run.id) : source?.previewUrl;
  const status = inference.starting
    ? live ? "Đang khởi tạo AI cho camera…" : video
      ? "Đang gửi video…"
      : "Đang gửi ảnh…"
    : run
      ? (
          {
            queued: "Đang chờ AI",
            running: live ? (result ? "AI đang xử lý camera…" : "Đang nạp model…") : video
              ? result
                ? "Đang xử lý video…"
                : "Đang nạp model…"
              : "Đang nạp model và xử lý ảnh…",
            completed: "Hoàn tất",
            failed: "Chạy thất bại",
            cancelled: "Đã dừng",
          } as const
        )[run.status]
      : "Sẵn sàng";
  function download() {
    if (!run) return;
    const blob = new Blob([JSON.stringify(run, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `visionkit-${run.id}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p role="status" className="text-sm text-muted-foreground">
          {status}
        </p>
        <div className="flex flex-wrap gap-2">
          {inference.active ? (
            <Button
              variant="outline"
              disabled={inference.stopping}
              onClick={() => void inference.stop()}
            >
              <SquareIcon />
              {live ? "Dừng AI" : "Dừng"}
            </Button>
          ) : (
            <Button
              disabled={!supported || !model || inference.starting}
              onClick={() => void inference.start()}
            >
              <PlayIcon />
              {run ? "Chạy lại" : "Chạy pipeline"}
            </Button>
          )}
          {result && (
            <Button variant="outline" onClick={download}>
              <DownloadIcon />
              {temporal ? "JSON frame cuối" : "JSON"}
            </Button>
          )}
        </div>
      </div>
      {!supported && (
        <p className="text-sm text-muted-foreground">
          Nguồn này chưa hỗ trợ chạy AI. Chọn ảnh, video file hoặc camera RTSP.
        </p>
      )}
      {(inference.error || run?.error) && (
        <p role="alert" className="text-sm text-destructive">
          {inference.error || run?.error}
        </p>
      )}
      {supported && (
        <RunMetrics result={result} progress={run?.progress} video={temporal} />
      )}
      {live && <p className="text-xs text-muted-foreground">AI lấy tối đa {parameters.liveFps} FPS · tối đa {parameters.liveMinutes} phút · tiếp tục chạy khi chuyển trang.</p>}
      {video && run?.progress && (
        <div className="space-y-2">
          <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground tabular-nums">
            <span>
              {run.progress.frames_processed} frame đã xử lý · Video gốc{" "}
              {(run.progress.source_fps ?? 0).toFixed(1)} FPS
            </span>
            <span>
              {run.progress.percent === null
                ? ""
                : `${run.progress.percent.toFixed(1)}%`}
            </span>
          </div>
          {run.progress.percent !== null && (
            <div
              role="progressbar"
              aria-label="Tiến độ xử lý video"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={run.progress.percent}
              className="h-1 overflow-hidden rounded bg-muted"
            >
              <div
                className="h-full bg-primary transition-[width] motion-reduce:transition-none"
                style={{ width: `${run.progress.percent}%` }}
              />
            </div>
          )}
        </div>
      )}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-3">
          {live && source ? (
            <LiveRunPreview sourceId={source.id} name={source.name} result={inference.active ? result : null} options={overlayOptions} />
          ) : src && supported && video ? (
            <VideoRunPreview
              key={run?.id ?? src}
              src={src}
              name={source?.name ?? "Video"}
              poster={source?.thumbnailUrl}
              result={result}
              options={overlayOptions}
              playing={run?.status === "running" && Boolean(run.result)}
            />
          ) : src && supported ? (
            <DetectionMedia
              kind="image"
              src={src}
              alt={`Kết quả ${source?.name ?? "ảnh"}`}
              result={result}
              options={overlayOptions}
              className="rounded-lg"
            />
          ) : (
            <div className="flex aspect-video items-center justify-center rounded-lg bg-muted text-sm text-muted-foreground">
              Chọn source để chạy inference
            </div>
          )}
          {video && (
            <p className="text-xs leading-5 text-muted-foreground">
              BBox theo kết quả mới nhất, có thể lệch nhẹ video.
            </p>
          )}
        </div>
        <aside
          aria-label="Tuỳ chọn hiển thị"
          className="min-w-0 space-y-4 border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
        >
          <OverlayControls
            preferences={preferences}
            onChange={updateOverlay}
            pose={pose}
            canConnect={canConnect}
            classify={model?.task === "classify"}
          />
          {result && temporal && (
            <div className="space-y-2 border-t pt-4 text-xs text-muted-foreground">
              <p>
                Frame {result.frameId ?? 0} ·{" "}
                {((result.timestampMs ?? 0) / 1000).toFixed(2)}s
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}


/** A new selection owns a new observer; prior server runs continue independently. */
export function RunWorkspace(props: Parameters<typeof RunWorkspaceContent>[0]) {
  const key = `${props.source?.id}:${props.model?.id}:${JSON.stringify(props.parameters)}`;
  return <RunWorkspaceContent key={key} {...props} />;
}
