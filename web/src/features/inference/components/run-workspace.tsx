"use client";
import {
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import {
  ArrowLeftRightIcon,
  CheckIcon,
  DownloadIcon,
  LoaderCircleIcon,
  PlayIcon,
  SquareIcon,
} from "lucide-react";
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
import { WebcamRunPreview } from "./webcam-run-preview";
import { RunMetrics } from "./run-metrics";
import { ResultCapture } from "@/features/media-capture/result-capture";

export type RunNavigation = { requestEdit: (step: number) => void };
const editLabels = ["đổi nguồn", "đổi model", "sửa thông số"];

function RunWorkspaceContent({
  source,
  model,
  parameters,
  onComplete,
  controlsTarget,
  navigationRef,
  onNavigate,
  onBusyChange,
  configuration,
  autoStart = false,
}: {
  source: VisionSource | null;
  model: StoredModel | null;
  parameters: YoloParameters;
  onComplete: () => Promise<void>;
  controlsTarget?: HTMLElement | null;
  navigationRef?: Ref<RunNavigation>;
  onNavigate: (step: number) => void;
  onBusyChange: (busy: boolean) => void;
  configuration?: ReactNode;
  autoStart?: boolean;
}) {
  const [captureToolbar, setCaptureToolbar] = useState<HTMLDivElement | null>(
    null,
  );
  const [editStep, setEditStep] = useState<number | null>(null);
  const confirmEdit = useRef<HTMLButtonElement>(null);
  const editOrigin = useRef<HTMLElement | null>(null);
  const inference = useInferenceRun(source, model?.id ?? null, parameters);
  const { run } = inference;
  const startHandled = useRef(false);
  useEffect(() => {
    if (!autoStart || startHandled.current || inference.recovering) return;
    startHandled.current = true;
    if (!inference.active) void inference.start();
  }, [autoStart, inference]);
  const busy =
    inference.starting ||
    inference.stopping ||
    inference.finishing ||
    inference.recovering;
  useEffect(() => {
    onBusyChange(busy);
    return () => onBusyChange(false);
  }, [busy, onBusyChange]);
  useEffect(() => {
    if (editStep !== null) confirmEdit.current?.focus();
  }, [editStep]);
  function requestEdit(target: number) {
    if (busy) return;
    if (inference.active) {
      editOrigin.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      setEditStep(target);
    } else onNavigate(target);
  }
  function cancelEdit() {
    setEditStep(null);
    requestAnimationFrame(() => editOrigin.current?.focus());
  }
  useImperativeHandle(navigationRef, () => ({ requestEdit }));
  async function stopAndEdit() {
    if (editStep === null || busy) return;
    if (!inference.active || (await inference.stop())) onNavigate(editStep);
  }
  const { preferences, update: updateOverlay } = useOverlayPreferences();
  const supported = Boolean(
    source &&
    ["image", "screen", "video", "stream", "youtube", "webcam"].includes(
      source.kind,
    ),
  );
  const video = source?.kind === "video" || source?.kind === "youtube";
  const webcam = source?.kind === "webcam";
  const live = source?.kind === "stream" || webcam;
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
    showSegments: model?.task === "segment" && preferences.segments,
    showLabels: preferences.boxes && preferences.labels,
    showKeypoints: preferences.keypoints,
    showSkeleton: preferences.skeleton,
    skeleton: canConnect ? COCO_POSE_SKELETON : [],
  };
  const src = webcam
    ? run?.result
      ? `${runPreview(run.id)}?frame=${run.result.frameId ?? 0}`
      : source?.previewUrl
    : live
      ? undefined
      : run
        ? runPreview(run.id)
        : source?.previewUrl;
  const status = inference.recovering
    ? "Đang khôi phục…"
    : inference.stopping
      ? "Đang dừng AI…"
      : inference.finishing
        ? "Đang kết thúc…"
        : inference.starting
          ? "Đang khởi tạo…"
          : run
            ? (
                {
                  queued: "Đang chờ AI",
                  running: result ? "Đang nhận diện" : "Đang nạp model…",
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
  const controls = (
    <div className="space-y-3">
      {editStep === null && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span
            role="status"
            className="inline-flex items-center gap-2 text-xs text-muted-foreground"
          >
            {busy ? (
              <LoaderCircleIcon className="size-3.5 animate-spin motion-reduce:animate-none" />
            ) : (
              <span
                className={`size-2 shrink-0 rounded-full ${inference.active ? "bg-success" : run?.status === "failed" ? "bg-destructive" : "bg-muted-foreground/50"}`}
              />
            )}
            {status}
          </span>
          <div
            className="flex flex-wrap items-center gap-2"
            role="group"
            aria-label="Điều khiển AI"
          >
            <Button
              size="lg"
              variant="outline"
              disabled={busy}
              onClick={() => requestEdit(0)}
            >
              <ArrowLeftRightIcon />
              Đổi nguồn
            </Button>
            {inference.active ? (
              <Button
                size="lg"
                variant="outline"
                disabled={busy}
                onClick={() => void inference.stop()}
              >
                <SquareIcon />
                {inference.stopping ? "Đang dừng…" : "Dừng AI"}
              </Button>
            ) : (
              <Button
                size="lg"
                disabled={!supported || !model || busy || editStep !== null}
                onClick={() => void inference.start()}
              >
                <PlayIcon />
                {inference.starting
                  ? "Đang khởi tạo…"
                  : run
                    ? "Chạy lại"
                    : "Chạy AI"}
              </Button>
            )}
          </div>
        </div>
      )}
      {editStep !== null && (
        <div
          role="region"
          aria-label="Dừng AI để chỉnh sửa"
          className="flex flex-wrap items-center justify-between gap-3"
        >
          <p className="text-sm">
            Dừng lượt hiện tại để {editLabels[editStep]}.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="lg"
              variant="ghost"
              disabled={busy}
              onClick={cancelEdit}
            >
              Tiếp tục xem
            </Button>
            <Button
              ref={confirmEdit}
              size="lg"
              disabled={busy}
              onClick={() => void stopAndEdit()}
            >
              <SquareIcon />
              {inference.stopping
                ? "Đang dừng…"
                : `Dừng AI và ${editLabels[editStep]}`}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
  return (
    <div className="space-y-4">
      {controlsTarget ? (
        createPortal(controls, controlsTarget)
      ) : controlsTarget === undefined ? (
        <div
          className="flex flex-wrap items-center gap-2"
          role="group"
          aria-label="Điều khiển pipeline"
        >
          {controls}
        </div>
      ) : null}
      {!supported && (
        <p className="text-sm text-muted-foreground">
          Chọn ảnh, video hoặc camera để chạy AI.
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
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_15rem]">
        <div className="min-w-0 space-y-3">
          <div className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span
              className="min-w-0 truncate font-medium text-foreground"
              title={source?.name}
            >
              {source?.name}
            </span>
            <span
              className="min-w-0 truncate"
              title={model?.name ?? model?.filename}
            >
              {model?.name ?? model?.filename}
            </span>
          </div>
          <ResultCapture
            key={run?.id ?? source?.id}
            name={source?.name ?? "ket-qua"}
            temporal={temporal}
            controlsTarget={captureToolbar}
          >
            {webcam ? (
              <WebcamRunPreview
                key={source?.id}
                src={src ?? ""}
                name={`Webcam ${source?.deviceIndex ?? 0} trên máy AI`}
                result={result}
                options={overlayOptions}
                active={inference.active}
              />
            ) : live && source ? (
              <LiveRunPreview
                sourceId={source.id}
                name={source.name}
                result={inference.active ? result : null}
                options={overlayOptions}
              />
            ) : src && supported && video ? (
              <VideoRunPreview
                key={run?.id ?? src}
                src={src}
                name={source?.name ?? "Video"}
                poster={source?.thumbnailUrl}
                result={result}
                options={overlayOptions}
                playing={Boolean(
                  run &&
                  ["running", "completed"].includes(run.status) &&
                  run.result,
                )}
              />
            ) : src && supported ? (
              <DetectionMedia
                kind="image"
                src={src}
                alt={`Kết quả ${source?.name ?? "ảnh"}`}
                result={result}
                options={overlayOptions}
                className="w-full rounded-lg"
              />
            ) : (
              <div className="flex aspect-video items-center justify-center rounded-lg bg-muted text-sm text-muted-foreground">
                Chọn nguồn để chạy AI
              </div>
            )}
          </ResultCapture>
          <div
            className="flex flex-wrap items-center gap-2 border-t pt-3"
            role="group"
            aria-label="Lưu kết quả"
          >
            <div ref={setCaptureToolbar} className="contents" />
            {result && (
              <Button
                size="lg"
                variant="ghost"
                disabled={inference.finishing}
                onClick={download}
                title={
                  temporal
                    ? "Tải kết quả frame cuối (JSON)"
                    : "Tải kết quả JSON"
                }
              >
                <DownloadIcon />
                Tải JSON
              </Button>
            )}
          </div>
        </div>
        <aside
          aria-label="Tuỳ chọn hiển thị"
          className="min-w-0 space-y-4 border-t pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-4"
        >
          <OverlayControls
            preferences={preferences}
            onChange={updateOverlay}
            pose={pose}
            segment={model?.task === "segment"}
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
          {live && (
            <p className="text-xs text-muted-foreground">
              {parameters.liveFps} FPS · {parameters.liveMinutes} phút
            </p>
          )}
          {configuration}
          {run && !inference.active && (
            <div className="border-t pt-4">
              <Button
                size="lg"
                variant="ghost"
                title="Dọn dữ liệu tạm và bắt đầu phiên mới"
                disabled={busy || editStep !== null}
                onClick={() => void inference.finish(onComplete)}
              >
                <CheckIcon />
                Kết thúc phiên
              </Button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

/** Selection keys isolate observers; route navigation still preserves server runs. */
export function RunWorkspace(props: Parameters<typeof RunWorkspaceContent>[0]) {
  const key = `${props.source?.id}:${props.model?.id}:${JSON.stringify(props.parameters)}`;
  return <RunWorkspaceContent key={key} {...props} />;
}
