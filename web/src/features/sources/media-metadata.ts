import type { SourceKind, VisionSource } from "./types";

type Metadata = Pick<VisionSource, "width" | "height" | "duration">;

export function readMediaMetadata(
  url: string,
  kind: SourceKind,
): Promise<Metadata> {
  return new Promise((resolve, reject) => {
    const media =
      kind === "image" ? new Image() : document.createElement("video");
    const cleanup = () => {
      window.clearTimeout(timeout);
      media.onload = null;
      media.onerror = null;
      if (media instanceof HTMLVideoElement) {
        media.onloadedmetadata = null;
        media.removeAttribute("src");
        media.load();
      }
    };
    const fail = () => {
      cleanup();
      reject(
        new Error(
          kind === "video"
            ? "Không đọc được video. Thử MP4 với codec H.264 hoặc WebM."
            : "Không đọc được ảnh. Thử tệp JPG hoặc PNG.",
        ),
      );
    };
    const timeout = window.setTimeout(fail, 15000);
    media.onerror = fail;
    if (media instanceof HTMLVideoElement) {
      media.preload = "metadata";
      media.onloadedmetadata = () => {
        const metadata = {
          width: media.videoWidth,
          height: media.videoHeight,
          duration: Number.isFinite(media.duration)
            ? media.duration
            : undefined,
        };
        cleanup();
        resolve(metadata);
      };
    } else {
      media.onload = () => {
        const metadata = {
          width: media.naturalWidth,
          height: media.naturalHeight,
        };
        cleanup();
        resolve(metadata);
      };
    }
    media.src = url;
  });
}

export function formatBytes(bytes?: number) {
  if (bytes === undefined) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDuration(seconds?: number) {
  if (seconds === undefined) return "Chưa xác định";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)
    .toString()
    .padStart(2, "0")}:${(whole % 60).toString().padStart(2, "0")}`;
}
