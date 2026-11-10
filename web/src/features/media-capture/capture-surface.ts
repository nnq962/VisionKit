import { computeMediaTransform } from "../vision-overlay/geometry.ts";

export type CaptureSurface = {
  media: HTMLVideoElement | HTMLImageElement | HTMLCanvasElement;
  overlay?: HTMLCanvasElement | null;
};

export function surfaceReady({ media }: CaptureSurface): boolean {
  if (media instanceof HTMLVideoElement)
    return media.readyState >= 2 && media.videoWidth > 0;
  if (media instanceof HTMLImageElement)
    return media.complete && media.naturalWidth > 0;
  return media.width > 0 && media.height > 0 && media.dataset.captureReady === "true";
}

/** Keep the displayed aspect ratio, at source resolution up to 1920px. */
export function captureSize({ media }: CaptureSurface) {
  const rect = media.getBoundingClientRect();
  if (!rect.width || !rect.height) throw new Error("Khung hình chưa sẵn sàng.");
  const width = media instanceof HTMLVideoElement ? media.videoWidth
    : media instanceof HTMLImageElement ? media.naturalWidth : media.width;
  const height = media instanceof HTMLVideoElement ? media.videoHeight
    : media instanceof HTMLImageElement ? media.naturalHeight : media.height;
  const scale = Math.min(
    Math.max(width / rect.width, height / rect.height),
    1920 / Math.max(rect.width, rect.height),
  );
  // Even dimensions also work with encoders that require chroma subsampling.
  return {
    width: Math.max(2, Math.round(rect.width * scale / 2) * 2),
    height: Math.max(2, Math.round(rect.height * scale / 2) * 2),
  };
}

/** Copy the visible media and its already-rendered overlay, including letterboxing. */
export function paintCapture(canvas: HTMLCanvasElement, surface: CaptureSurface) {
  if (!surfaceReady(surface)) throw new Error("Chưa có hình ảnh để lưu.");
  const { media, overlay } = surface;
  const rect = media.getBoundingClientRect();
  if (!rect.width || !rect.height) throw new Error("Khung hình không còn hiển thị.");
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Trình duyệt không tạo được ảnh kết quả.");
  const width = media instanceof HTMLVideoElement ? media.videoWidth
    : media instanceof HTMLImageElement ? media.naturalWidth : media.width;
  const height = media instanceof HTMLVideoElement ? media.videoHeight
    : media instanceof HTMLImageElement ? media.naturalHeight : media.height;
  const style = getComputedStyle(media);
  const position = style.objectPosition.split(" ").map((part) => parseFloat(part) / 100);
  const transform = computeMediaTransform({
    viewportWidth: rect.width,
    viewportHeight: rect.height,
    mediaWidth: width,
    mediaHeight: height,
    fit: style.objectFit === "cover" || style.objectFit === "fill" ? style.objectFit : "contain",
    position: { x: position[0] ?? 0.5, y: position[1] ?? 0.5 },
  });
  if (!transform) throw new Error("Kích thước khung hình không hợp lệ.");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.fillStyle = "#09090b";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.scale(canvas.width / rect.width, canvas.height / rect.height);
  ctx.save();
  if (media.style.transform === "scaleX(-1)") {
    ctx.translate(rect.width, 0);
    ctx.scale(-1, 1);
  }
  ctx.drawImage(media, transform.x, transform.y, transform.width, transform.height);
  ctx.restore();
  if (overlay && overlay.width && overlay.height) {
    const overlayRect = overlay.getBoundingClientRect();
    ctx.drawImage(overlay, overlayRect.left - rect.left, overlayRect.top - rect.top, overlayRect.width, overlayRect.height);
  }
  ctx.restore();
}
