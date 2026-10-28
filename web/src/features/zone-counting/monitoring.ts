import type { CountResult, MonitorSettings } from "./types";

/** Chỉ cộng những vùng đang hiển thị; null thể hiện số đếm không khả dụng. */
export function regionTotals(
  counts: CountResult | null,
  classes: string[],
  ids: string[],
): (number | null)[] {
  return classes.map((label) => {
    if (!counts?.valid || !ids.length) return null;
    const rows = ids.map((id) => counts.regions.find((row) => row.id === id));
    if (rows.some((row) => !row)) return null;
    const values = rows
      .map((row) => row!.counts[label])
      .filter((value) => value != null);
    return values.length
      ? values.reduce((total, value) => total + value, 0)
      : null;
  });
}

export function validateMonitorSettings(settings: MonitorSettings): string {
  if (!settings.model_id) return "Chọn model YOLOE trước khi lưu.";
  if (settings.auto_start && !settings.continuous)
    return "Bật Chạy liên tục trước khi bật Tự khởi động.";
  if (
    ![settings.options.conf, settings.options.iou].every(
      (value) => Number.isFinite(value) && value >= 0 && value <= 1,
    )
  )
    return "Confidence và IoU phải từ 0 đến 1.";
  if (
    !Number.isFinite(settings.options.max_fps) ||
    settings.options.max_fps < 1 ||
    settings.options.max_fps > 60
  )
    return "Giới hạn AI phải từ 1 đến 60 FPS.";
  if (
    !Number.isInteger(settings.duration_seconds / 60) ||
    settings.duration_seconds < 60 ||
    settings.duration_seconds > 14400
  )
    return "Thời lượng mỗi lượt từ 1 đến 240 phút.";
  return "";
}
