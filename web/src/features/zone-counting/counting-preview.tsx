"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent,
} from "react";
import { useVideoStream } from "@/features/video-stream";
import { useDetectionOverlay } from "@/features/vision-overlay";
import {
  computeMediaTransform,
  projectPoint,
} from "@/features/vision-overlay/geometry";
import { runPreview, type InferenceResult } from "@/features/inference/api";
import type { VisionSource } from "@/features/sources/types";
import type { CountingRun, CountingZone, Point } from "./types";
import { regionPoint } from "./geometry";

export function CountingPreview({
  source,
  run,
  zones,
  selected,
  draft,
  editable,
  interactionDisabled = false,
  boxes,
  labels,
  segments,
  anchors,
  showZones = true,
  showIdleHint = true,
  onSelect,
  onPoint,
  onMove,
  onDimensions,
  onConnection,
}: {
  source: VisionSource;
  run: CountingRun | null;
  zones: CountingZone[];
  selected: string | null;
  draft: Point[] | null;
  editable: boolean;
  interactionDisabled?: boolean;
  boxes: boolean;
  labels: boolean;
  segments: boolean;
  anchors: boolean;
  showZones?: boolean;
  showIdleHint?: boolean;
  onSelect: (id: string) => void;
  onPoint: (point: Point) => void;
  onMove: (id: string, index: number, point: Point) => void;
  onDimensions: (width: number, height: number) => void;
  onConnection: (connected: boolean) => void;
}) {
  const canInteract = editable && !interactionDisabled;
  const live = source.kind === "stream";
  const stream = useVideoStream(live ? source.id : null);
  const video = useRef<HTMLVideoElement | null>(null);
  const container = useRef<HTMLDivElement | null>(null);
  const [viewport, setViewport] = useState({ width: 640, height: 360 });
  const [dimensions, setDimensions] = useState({
    width: source.width ?? 0,
    height: source.height ?? 0,
  });
  const [error, setError] = useState("");
  const [syncedFrame, setSyncedFrame] = useState<number | string | null>(null);
  const positionedRun = useRef<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const overlay = useRef<SVGSVGElement | null>(null);
  const dragging = useRef<{
    id: string;
    index: number;
    pointerId: number;
  } | null>(null);
  const drawingTap = useRef<{ pointerId: number; x: number; y: number } | null>(
    null,
  );
  const active = run?.status === "running" || run?.status === "queued";
  const result = run?.result ?? null;
  const playVideo = !live && active && Boolean(result);
  const displayResult: InferenceResult | null = live
    ? stream.status === "playing" && run?.status === "running"
      ? result
      : null
    : playVideo && playing
      ? result
      : result && syncedFrame === result.frameId
        ? result
        : null;
  const { mediaRef, canvasRef, canvasStyle } = useDetectionOverlay({
    result: displayResult,
    options: {
      showBoxes: boxes,
      showLabels: labels,
      showSegments: segments,
      showKeypoints: false,
      showSkeleton: false,
    },
    staleAfterMs: live ? 2500 : playVideo ? 2000 : 0,
  });
  const bindVideo = useCallback(
    (element: HTMLVideoElement | null) => {
      video.current = element;
      mediaRef(element);
    },
    [mediaRef],
  );
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(() =>
      setViewport({ width: element.clientWidth, height: element.clientHeight }),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    onConnection(!live || stream.status === "playing");
  }, [live, stream.status, onConnection]);
  useEffect(() => {
    if (!live || !video.current) return;
    const element = video.current;
    element.srcObject = stream.mediaStream;
    if (stream.mediaStream) void element.play().catch(() => {});
    return () => {
      element.srcObject = null;
    };
  }, [live, stream.mediaStream]);
  const syncVideo = useCallback(
    (element: HTMLVideoElement) => {
      if (live || !result || element.readyState < 1) return;
      const timestamp = Math.max(0, (result.timestampMs ?? 0) / 1000);
      if (playVideo) {
        // Giống YOLO pipeline: đặt vị trí ban đầu rồi phát liên tục.
        if (positionedRun.current !== run?.id) {
          element.currentTime = timestamp;
          positionedRun.current = run?.id ?? null;
        }
        if (element.paused && !element.ended) {
          void element
            .play()
            .catch(() => setError("Bấm Phát video để tiếp tục preview."));
        }
      } else {
        element.pause();
        if (Math.abs(element.currentTime - timestamp) > 0.025)
          element.currentTime = timestamp;
        else setSyncedFrame(result.frameId ?? null);
      }
    },
    [live, result, playVideo, run?.id],
  );
  useEffect(() => {
    if (video.current) syncVideo(video.current);
  }, [syncVideo]);
  const transform =
    dimensions.width && dimensions.height
      ? computeMediaTransform({
          viewportWidth: viewport.width,
          viewportHeight: viewport.height,
          mediaWidth: dimensions.width,
          mediaHeight: dimensions.height,
        })
      : null;
  const project = (point: Point) =>
    transform
      ? projectPoint(point[0], point[1], dimensions, transform, true)!
      : { x: 0, y: 0 };
  const pointer = (event: PointerEvent<SVGSVGElement>, clamp = false) => {
    if (!transform) return null;
    const rect = event.currentTarget.getBoundingClientRect();
    return regionPoint(
      event.clientX - rect.left,
      event.clientY - rect.top,
      transform,
      clamp,
    );
  };
  return (
    <div className="space-y-3">
      <div
        ref={container}
        className="relative aspect-video overflow-hidden rounded-lg bg-muted"
      >
        <video
          ref={bindVideo}
          src={live ? undefined : run ? runPreview(run.id) : source.previewUrl}
          muted
          playsInline
          autoPlay={live}
          controls={!live && !active && !result && draft === null}
          preload="auto"
          aria-label={`Nguồn đếm ${source.name}`}
          className="size-full object-contain"
          onLoadedMetadata={(event) => {
            const element = event.currentTarget;
            setDimensions({
              width: element.videoWidth,
              height: element.videoHeight,
            });
            onDimensions(element.videoWidth, element.videoHeight);
            syncVideo(element);
          }}
          onPlaying={() => {
            setPlaying(true);
            setError("");
          }}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onSeeking={() => {
            if (!playVideo) setSyncedFrame(null);
          }}
          onSeeked={(event) => {
            if (
              !playVideo &&
              result &&
              Math.abs(
                event.currentTarget.currentTime -
                  (result.timestampMs ?? 0) / 1000,
              ) < 0.15
            )
              setSyncedFrame(result.frameId ?? null);
          }}
          onError={() =>
            setError("Không phát được video. Kiểm tra file hoặc codec H.264.")
          }
        />
        {error && playVideo && (
          <button
            type="button"
            className="absolute bottom-3 left-3 z-10 rounded-md bg-background px-3 py-2 text-sm"
            onClick={() => {
              if (video.current) syncVideo(video.current);
            }}
          >
            Phát video
          </button>
        )}
        <canvas ref={canvasRef} style={canvasStyle} aria-hidden="true" />
        {transform && (
          <svg
            ref={overlay}
            aria-label="Vẽ vùng polygon"
            role="img"
            viewBox={`0 0 ${viewport.width} ${viewport.height}`}
            preserveAspectRatio="none"
            className={`absolute inset-0 size-full ${editable && draft !== null ? "cursor-crosshair touch-none" : editable ? "touch-none" : "pointer-events-none"}`}
            style={{
              pointerEvents: canInteract && draft !== null ? "auto" : "none",
            }}
            onPointerDown={(event) => {
              if (!canInteract || draft === null || !event.isPrimary) return;
              if (event.pointerType === "mouse" && event.button !== 0) return;
              event.preventDefault();
              if (!live) video.current?.pause();
              drawingTap.current = {
                pointerId: event.pointerId,
                x: event.clientX,
                y: event.clientY,
              };
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (
                !canInteract ||
                dragging.current?.pointerId !== event.pointerId
              )
                return;
              event.preventDefault();
              const point = pointer(event, true);
              if (point)
                onMove(dragging.current.id, dragging.current.index, point);
            }}
            onPointerUp={(event) => {
              const tap = drawingTap.current;
              drawingTap.current = null;
              dragging.current = null;
              if (
                canInteract &&
                draft !== null &&
                tap?.pointerId === event.pointerId &&
                Math.hypot(event.clientX - tap.x, event.clientY - tap.y) <= 12
              ) {
                const point = pointer(event);
                if (point) {
                  const last = draft.at(-1);
                  const projected = last ? project(last) : null;
                  const rect = event.currentTarget.getBoundingClientRect();
                  if (
                    !projected ||
                    Math.hypot(
                      event.clientX - rect.left - projected.x,
                      event.clientY - rect.top - projected.y,
                    ) >= 10
                  )
                    onPoint(point);
                }
              }
              if (event.currentTarget.hasPointerCapture(event.pointerId))
                event.currentTarget.releasePointerCapture(event.pointerId);
            }}
            onPointerCancel={() => {
              dragging.current = null;
              drawingTap.current = null;
            }}
            onLostPointerCapture={() => {
              dragging.current = null;
              drawingTap.current = null;
            }}
          >
            {showZones &&
              zones.map((zone) => {
                const points = zone.points.map(project);
                return (
                  <g key={zone.id}>
                    <polygon
                      points={points.map((p) => `${p.x},${p.y}`).join(" ")}
                      fill={zone.color}
                      fillOpacity={0.08}
                      style={{
                        pointerEvents:
                          canInteract && draft === null ? "all" : "none",
                        touchAction: canInteract ? "none" : "auto",
                      }}
                      stroke={zone.color}
                      strokeWidth={selected === zone.id ? 3 : 2}
                      onPointerDown={(event) => {
                        if (draft === null && canInteract) {
                          event.preventDefault();
                          event.stopPropagation();
                          if (!live) video.current?.pause();
                          onSelect(zone.id);
                        }
                      }}
                    />
                    <text
                      x={points[0].x + 6}
                      y={Math.max(16, points[0].y - 6)}
                      fill={zone.color}
                      stroke="#0f172a"
                      strokeWidth={3}
                      paintOrder="stroke"
                      fontSize={13}
                      fontWeight={600}
                      style={{ pointerEvents: "none" }}
                    >
                      {zone.name}
                    </text>
                    {editable &&
                      draft === null &&
                      zone.id === selected &&
                      points.map((p, index) => (
                        <g
                          key={index}
                          aria-label={`Đỉnh ${index + 1} của ${zone.name}`}
                          className="cursor-move touch-none"
                          style={{
                            pointerEvents: canInteract ? "all" : "none",
                            touchAction: "none",
                          }}
                          onPointerDown={(event) => {
                            if (!canInteract || !event.isPrimary) return;
                            event.preventDefault();
                            event.stopPropagation();
                            if (!live) video.current?.pause();
                            drawingTap.current = null;
                            dragging.current = {
                              id: zone.id,
                              index,
                              pointerId: event.pointerId,
                            };
                            overlay.current?.setPointerCapture(event.pointerId);
                          }}
                        >
                          <circle cx={p.x} cy={p.y} r={22} fill="transparent" />
                          <circle
                            cx={p.x}
                            cy={p.y}
                            r={7}
                            fill="white"
                            stroke={zone.color}
                            strokeWidth={2}
                            pointerEvents="none"
                          />
                        </g>
                      ))}
                  </g>
                );
              })}
            {anchors &&
              displayResult?.detections.map((item, index) => {
                const box = item.bbox;
                if (!box || !box.every(Number.isFinite)) return null;
                const point = project([
                  Math.max(
                    0,
                    Math.min(
                      1,
                      (box[0] + box[2]) / (2 * displayResult.sourceSize.width),
                    ),
                  ),
                  Math.max(
                    0,
                    Math.min(1, box[3] / displayResult.sourceSize.height),
                  ),
                ]);
                return (
                  <circle
                    key={`anchor-${index}`}
                    cx={point.x}
                    cy={point.y}
                    r={4}
                    fill="white"
                    stroke="#0f172a"
                    strokeWidth={1.5}
                    pointerEvents="none"
                  >
                    <title>{item.label} · điểm đếm</title>
                  </circle>
                );
              })}
            {draft && (
              <g pointerEvents="none">
                <polyline
                  points={draft
                    .map(project)
                    .map((p) => `${p.x},${p.y}`)
                    .join(" ")}
                  fill="none"
                  stroke="#fbbf24"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                />
                {draft.map((p, i) => (
                  <circle
                    key={i}
                    cx={project(p).x}
                    cy={project(p).y}
                    r={5}
                    fill="#fbbf24"
                  />
                ))}
              </g>
            )}
          </svg>
        )}
        {live && stream.status !== "playing" && (
          <div
            role="status"
            className="absolute inset-0 flex items-center justify-center bg-background/80 p-6 text-center text-sm"
          >
            {stream.error ?? "Đang kết nối camera…"}
          </div>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {live ? (
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>
            {stream.status === "playing"
              ? "Camera đang phát"
              : "Chưa có hình camera"}
          </span>
          <button className="underline" onClick={stream.reconnect}>
            Kết nối lại preview
          </button>
          <button className="underline" onClick={stream.stop}>
            Dừng preview
          </button>
        </div>
      ) : showIdleHint || result ? (
        <p className="text-xs text-muted-foreground">
          {result
            ? playVideo
              ? "BBox cập nhật theo AI, có thể lệch video."
              : "Kết quả frame cuối."
            : editable
              ? "Chọn khung hình → Vẽ vùng."
              : "Kiểm tra vùng trước khi chạy."}
        </p>
      ) : null}
    </div>
  );
}
