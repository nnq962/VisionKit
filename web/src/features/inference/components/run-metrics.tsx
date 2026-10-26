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
}: {
  result: InferenceResult | null;
  progress: InferenceRun["progress"];
  video: boolean;
}) {
  const topClass = result?.classifications?.[0];
  const elapsed = result ? `${number(result.elapsedMs / 1000, 2)} s` : "—";
  const metrics = [
    {
      label: video ? "Suy luận / frame" : "Suy luận",
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
      label: topClass ? "Độ tin cậy" : "Đối tượng phát hiện",
      value: topClass
        ? `${number(topClass.confidence * 100)}%`
        : result
          ? number(result.detections.length, 0)
          : "—",
      detail: topClass?.label ?? (video ? "Trong frame mới nhất" : "Trong ảnh"),
    },
    {
      label: "Thiết bị thực thi",
      value: result?.device ?? "—",
      detail: result
        ? `Ảnh gốc ${result.sourceSize.width} × ${result.sourceSize.height}`
        : "Được xác nhận khi có kết quả",
    },
  ];
  return (
    <dl
      aria-label="Hiệu năng suy luận"
      className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4"
    >
      {metrics.map((metric) => (
        <div
          key={metric.label}
          title={metric.title}
          className="min-w-0 rounded-lg border bg-muted/20 p-4"
        >
          <dt className="text-xs text-muted-foreground">{metric.label}</dt>
          <dd className="mt-2 break-words text-xl font-semibold tabular-nums">
            {metric.value}
          </dd>
          <dd className="mt-1 break-words text-xs leading-5 text-muted-foreground">
            {metric.detail}
          </dd>
        </div>
      ))}
    </dl>
  );
}
