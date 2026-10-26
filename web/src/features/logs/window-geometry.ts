export type ResizeDirection = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";
export type WindowBounds = { x: number; y: number; width: number; height: number };
export const WINDOW_MARGIN = 12;
export const MIN_WINDOW_WIDTH = 360;
export const MIN_WINDOW_HEIGHT = 300;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), Math.max(min, max));

export function resizeWindow(initial: WindowBounds, direction: ResizeDirection,
  dx: number, dy: number, viewport: { width: number; height: number }): WindowBounds {
  const minWidth = Math.min(MIN_WINDOW_WIDTH, viewport.width - WINDOW_MARGIN * 2);
  const minHeight = Math.min(MIN_WINDOW_HEIGHT, viewport.height - WINDOW_MARGIN * 2);
  let left = initial.x;
  let top = initial.y;
  let right = left + initial.width;
  let bottom = top + initial.height;
  if (direction.includes("e")) right = clamp(right + dx, left + minWidth, viewport.width - WINDOW_MARGIN);
  if (direction.includes("w")) left = clamp(left + dx, WINDOW_MARGIN, right - minWidth);
  if (direction.includes("s")) bottom = clamp(bottom + dy, top + minHeight, viewport.height - WINDOW_MARGIN);
  if (direction.includes("n")) top = clamp(top + dy, WINDOW_MARGIN, bottom - minHeight);
  return { x: left, y: top, width: right - left, height: bottom - top };
}
