import type { MediaFit } from "./types";

export type MediaTransform = {
  x: number;
  y: number;
  width: number;
  height: number;
  clip: { x: number; y: number; width: number; height: number };
};

/** Tính vùng ảnh thực trong element, bao gồm letterbox/crop, theo CSS pixel. */
export function computeMediaTransform({
  viewportWidth,
  viewportHeight,
  mediaWidth,
  mediaHeight,
  fit = "contain",
  x = 0,
  y = 0,
  position = { x: 0.5, y: 0.5 },
}: {
  viewportWidth: number;
  viewportHeight: number;
  mediaWidth: number;
  mediaHeight: number;
  fit?: MediaFit;
  x?: number;
  y?: number;
  position?: { x: number; y: number };
}): MediaTransform | null {
  if (
    ![viewportWidth, viewportHeight, mediaWidth, mediaHeight].every(
      (value) => Number.isFinite(value) && value > 0,
    ) ||
    ![x, y, position.x, position.y].every(Number.isFinite)
  )
    return null;
  const ratio =
    fit === "cover"
      ? Math.max(viewportWidth / mediaWidth, viewportHeight / mediaHeight)
      : Math.min(viewportWidth / mediaWidth, viewportHeight / mediaHeight);
  const width = fit === "fill" ? viewportWidth : mediaWidth * ratio;
  const height = fit === "fill" ? viewportHeight : mediaHeight * ratio;
  const left = x + (viewportWidth - width) * position.x;
  const top = y + (viewportHeight - height) * position.y;
  const clipX = Math.max(x, left),
    clipY = Math.max(y, top);
  return {
    x: left,
    y: top,
    width,
    height,
    clip: {
      x: clipX,
      y: clipY,
      width: Math.max(0, Math.min(x + viewportWidth, left + width) - clipX),
      height: Math.max(0, Math.min(y + viewportHeight, top + height) - clipY),
    },
  };
}

/** Đổi pixel gốc hoặc toạ độ 0–1 sang CSS pixel, lật ngang nếu media cũng bị lật. */
export function projectPoint(
  x: number,
  y: number,
  sourceSize: { width: number; height: number },
  transform: MediaTransform,
  normalized = false,
  mirrored = false,
): { x: number; y: number } | null {
  if (
    ![x, y, sourceSize.width, sourceSize.height].every(Number.isFinite) ||
    sourceSize.width <= 0 ||
    sourceSize.height <= 0
  )
    return null;
  const nx = normalized ? x : x / sourceSize.width;
  const ny = normalized ? y : y / sourceSize.height;
  return {
    x: transform.x + (mirrored ? 1 - nx : nx) * transform.width,
    y: transform.y + ny * transform.height,
  };
}
