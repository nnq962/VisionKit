import type { InferenceResult, InferenceRun } from "../api";

function number(value: number | undefined, digits = 1) {
  return value !== undefined && Number.isFinite(value) && value >= 0
    ? value.toLocaleString("vi-VN", { maximumFractionDigits: digits })
    : "—";
}

export function RunMetrics({
  result,
  progress,
  video,
  compact = false,
}: {
  result: InferenceResult | null;
  progress: InferenceRun["progress"];
  video: boolean;
  compact?: boolean;
}) {
  const topClass = result?.classifications?.[0];
  const elapsed = result ? `${number(result.elapsedMs / 1000, 2)} s` : "—";
  const metrics = [
    {
      label: video ? "AI / khung hình" : "Thời gian AI",
      value: result ? `${number(result.speed.inference)} ms` : "—",
      detail: result
        ? `Tiền xử lý ${number(result.speed.preprocess)} ms · Hậu xử lý ${number(result.speed.postprocess)} ms`
        : "Chờ kết quả AI",
      title: "Thời gian AI xử lý ảnh hoặc frame mới nhất; không gồm nạp model.",
    },
    {
      label: video ? "Tốc độ xử lý" : "Thời gian xử lý",
      value: video
        ? progress
          ? `${number(progress.processing_fps)} FPS`
          : "—"
        : elapsed,
      detail: video ? `Đã xử lý trong ${elapsed}` : "Gồm nạp model và suy luận",
      title: video
        ? "Số frame đã suy luận / thời gian xử lý, gồm chờ theo nhịp video; không phải FPS tối đa của model."
        : "Thời gian xử lý tại AI, không gồm tải tệp và truyền kết quả.",
    },
    {
      label: topClass ? "Độ tin cậy" : "Đối tượng",
      value: topClass
        ? `${number(topClass.confidence * 100)}%`
        : result
          ? number(result.detections.length, 0)
          : "—",
      detail: topClass?.label ?? (video ? "Trong frame mới nhất" : "Trong ảnh"),
    },
    {
      label: "Thiết bị",
      value: result?.device ?? "—",
      detail: result
        ? `Ảnh gốc ${result.sourceSize.width} × ${result.sourceSize.height}`
        : "Được xác nhận khi có kết quả",
    },
  ];
  return (
    <dl
      aria-label="Hiệu năng suy luận"
      className={`grid grid-cols-2 gap-x-4 gap-y-3 ${compact ? "" : "border-b pb-4 sm:grid-cols-4"}`}
    >
      {metrics.map((metric) => (
        <div
          key={metric.label}
          title={[metric.title, metric.detail].filter(Boolean).join(" ")}
          className="grid min-w-0 gap-1 text-left"
        >
          <dt
            title={metric.label}
            className="truncate text-xs leading-4 text-muted-foreground"
          >
            {metric.label}
          </dt>
          <dd
            title={metric.value}
            className="min-w-0 truncate text-base leading-5 font-semibold tabular-nums"
          >
            {metric.value}
          </dd>
          <dd className="sr-only">{metric.detail}</dd>
        </div>
      ))}
    </dl>
  );
}
