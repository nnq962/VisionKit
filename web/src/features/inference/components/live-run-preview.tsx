"use client";

import { useCallback, useEffect, useRef } from "react";
import { useVideoStream } from "@/features/video-stream";
import { useDetectionOverlay } from "@/features/vision-overlay";
import type { DetectionFrame, OverlayOptions } from "@/features/vision-overlay/types";

/** WebRTC video and JSON-only AI overlay share geometry, never re-encode video. */
export function LiveRunPreview({
  sourceId,
  name,
  result,
  options,
}: {
  sourceId: string;
  name: string;
  result: DetectionFrame | null;
  options: OverlayOptions;
}) {
  const stream = useVideoStream(sourceId);
  const video = useRef<HTMLVideoElement | null>(null);
  const { mediaRef, canvasRef, canvasStyle } = useDetectionOverlay({
    result: stream.status === "playing" ? result : null,
    options,
    staleAfterMs: 2000,
  });
  const bind = useCallback(
    (element: HTMLVideoElement | null) => {
      video.current = element;
      mediaRef(element);
    },
    [mediaRef],
  );
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    element.srcObject = stream.mediaStream;
    if (stream.mediaStream) void element.play().catch(() => {});
    return () => {
      element.srcObject = null;
    };
  }, [stream.mediaStream]);
  return (
    <div className="space-y-3">
      <div className="relative aspect-video overflow-hidden rounded-lg bg-muted">
        <video
          ref={bind}
          autoPlay
          muted
          playsInline
          aria-label={`AI trực tiếp ${name}`}
          className="size-full object-contain"
        />
        <canvas ref={canvasRef} style={canvasStyle} aria-hidden="true" />
        {stream.status !== "playing" && (
          <p role="status" className="absolute inset-0 flex items-center justify-center bg-background/90 px-6 text-center text-sm text-muted-foreground">
            {stream.error ?? "Đang kết nối video…"}
          </p>
        )}
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        BBox theo frame mới nhất, có thể trễ nhẹ và tự xoá khi kết quả cũ.
      </p>
    </div>
  );
}
