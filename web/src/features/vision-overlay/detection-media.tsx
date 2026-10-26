"use client";

/* eslint-disable @next/next/no-img-element -- media gốc dùng chung hình học với canvas. */
import type {
  CSSProperties,
  ImgHTMLAttributes,
  VideoHTMLAttributes,
} from "react";
import { cn } from "@/lib/utils";
import { useDetectionOverlay } from "./use-detection-overlay";
import type { DetectionFrame, MediaFit, OverlayOptions } from "./types";

type BaseProps = {
  src: string;
  result?: DetectionFrame | null;
  options?: OverlayOptions;
  staleAfterMs?: number;
  fit?: MediaFit;
  className?: string;
  style?: CSSProperties;
};
export type DetectionMediaProps = BaseProps &
  (
    | {
        kind: "image";
        alt: string;
        imageProps?: Omit<
          ImgHTMLAttributes<HTMLImageElement>,
          "src" | "alt" | "className" | "style" | "width" | "height" | "srcSet"
        >;
      }
    | {
        kind: "video";
        label: string;
        videoProps?: Omit<
          VideoHTMLAttributes<HTMLVideoElement>,
          "src" | "className" | "style" | "width" | "height" | "children"
        >;
      }
  );

/** Media gốc và canvas nằm chung wrapper; không vẽ lại/video-encode từng frame. */
export function DetectionMedia(props: DetectionMediaProps) {
  // Đổi source/kind huỷ canvas và kết quả cũ, không mang bbox sang media khác.
  return <MediaSurface key={`${props.kind}:${props.src}`} {...props} />;
}

function MediaSurface(props: DetectionMediaProps) {
  const { mediaRef, canvasRef, canvasStyle } = useDetectionOverlay(props);
  const position = props.options?.position ?? { x: 0.5, y: 0.5 };
  const mediaStyle: CSSProperties = {
    width: "100%",
    height: "100%",
    display: "block",
    objectFit: props.fit ?? "contain",
    objectPosition: `${position.x * 100}% ${position.y * 100}%`,
    transform: props.options?.mirrored ? "scaleX(-1)" : undefined,
  };
  return (
    <div
      className={cn(
        "relative aspect-video overflow-hidden bg-muted",
        props.className,
      )}
      style={props.style}
    >
      {props.kind === "image" ? (
        <img
          {...props.imageProps}
          ref={mediaRef}
          src={props.src}
          alt={props.alt}
          style={mediaStyle}
        />
      ) : (
        <video
          controls
          playsInline
          {...props.videoProps}
          ref={mediaRef}
          src={props.src}
          aria-label={props.label}
          style={mediaStyle}
        />
      )}
      <canvas ref={canvasRef} style={canvasStyle} aria-hidden="true" />
    </div>
  );
}
