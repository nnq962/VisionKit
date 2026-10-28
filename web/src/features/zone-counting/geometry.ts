import type { Point } from "./types";
import type { MediaTransform } from "../vision-overlay/geometry";

/** Đổi con trỏ CSS sang toạ độ ảnh; bỏ click trong viền đen. */
export function regionPoint(
  x: number,
  y: number,
  transform: MediaTransform,
  clamp = false,
): Point | null {
  const nx = (x - transform.x) / transform.width,
    ny = (y - transform.y) / transform.height;
  if (!Number.isFinite(nx) || !Number.isFinite(ny)) return null;
  if (!clamp && (nx < 0 || ny < 0 || nx > 1 || ny > 1)) return null;
  return [Math.max(0, Math.min(1, nx)), Math.max(0, Math.min(1, ny))];
}

/** Kiểm tra nhanh vùng trước khi gửi backend; server kiểm tra lại toàn bộ hình học. */
export function polygonError(points: Point[]): string {
  if (points.length < 3 || points.length > 32)
    return "Vùng cần từ 3 đến 32 đỉnh.";
  if (
    points.some(
      (point) =>
        point.length !== 2 ||
        point.some(
          (value) => !Number.isFinite(value) || value < 0 || value > 1,
        ),
    )
  )
    return "Đỉnh vùng phải nằm trong khung hình.";
  const cross = (a: Point, b: Point, c: Point) =>
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const on = (p: Point, a: Point, b: Point) =>
    Math.abs(cross(a, b, p)) < 1e-9 &&
    p.every(
      (v, i) =>
        v >= Math.min(a[i], b[i]) - 1e-9 && v <= Math.max(a[i], b[i]) + 1e-9,
    );
  const n = points.length;
  if (new Set(points.map((p) => p.join(","))).size !== n)
    return "Vùng không được trùng đỉnh.";
  const area = points.reduce(
    (sum, p, i) =>
      sum + p[0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * p[1],
    0,
  );
  if (Math.abs(area) < 1e-6)
    return "Vùng không có diện tích hoặc các đỉnh đang tự cắt.";
  for (let i = 0; i < n; i++) {
    const a = points[i],
      b = points[(i + 1) % n],
      next = points[(i + 2) % n];
    if (
      Math.abs(cross(a, b, next)) < 1e-9 &&
      (on(next, a, b) || on(a, b, next))
    )
      return "Các cạnh không được gập ngược lên nhau.";
    for (let j = i + 1; j < n; j++) {
      if (j === i + 1 || (i === 0 && j === n - 1)) continue;
      const c = points[j],
        d = points[(j + 1) % n];
      if (
        (cross(a, b, c) * cross(a, b, d) < 0 &&
          cross(c, d, a) * cross(c, d, b) < 0) ||
        on(a, c, d) ||
        on(b, c, d) ||
        on(c, a, b) ||
        on(d, a, b)
      )
        return "Vùng không được tự cắt hoặc chạm cạnh.";
    }
  }
  return "";
}
