import { DownloadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/features/sources/media-metadata";
import type { ModelDownload } from "../api";
import type { ModelVariant } from "../catalog";

const labels = {
  queued: "Đang chờ",
  downloading: "Đang tải",
  completed: "Đã lưu",
  failed: "Tải thất bại",
  cancelled: "Đã huỷ",
};
export function ModelDownloadList({
  jobs,
  busy,
  onCancel,
  onRetry,
}: {
  jobs: ModelDownload[];
  busy: string[];
  onCancel: (id: string) => void;
  onRetry: (variant: ModelVariant) => void;
}) {
  if (!jobs.length)
    return (
      <div className="flex min-h-56 flex-col items-center justify-center gap-3 text-center text-muted-foreground">
        <DownloadIcon className="size-8" strokeWidth={1.5} />
        <p className="text-sm">Chưa có lượt tải</p>
      </div>
    );
  return (
    <ul className="divide-y" aria-label="Các lượt tải model">
      {jobs.map((job) => {
        const active = ["queued", "downloading"].includes(job.status);
        return (
          <li key={job.jobId} className="space-y-3 py-5 first:pt-0 last:pb-0">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="break-all text-sm font-medium">
                  {job.variant.filename}
                </p>
                <p className="text-xs tabular-nums text-muted-foreground">
                  {labels[job.status]} · {formatBytes(job.received)} /{" "}
                  {formatBytes(job.total)}
                  {active ? ` · ${job.progress}%` : ""}
                </p>
              </div>
              {active ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy.includes(job.variant.id)}
                  onClick={() => onCancel(job.variant.id)}
                >
                  Huỷ tải
                </Button>
              ) : ["failed", "cancelled"].includes(job.status) ? (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy.includes(job.variant.id)}
                  onClick={() => onRetry(job.variant)}
                >
                  Thử lại
                </Button>
              ) : null}
            </div>
            {active && (
              <div
                role="progressbar"
                aria-label={`Tiến độ lượt tải ${job.variant.filename}`}
                aria-valuenow={job.progress}
                aria-valuemin={0}
                aria-valuemax={100}
                className="h-1 overflow-hidden rounded bg-muted"
              >
                <div
                  style={{ width: `${job.progress}%` }}
                  className="h-full bg-primary transition-[width] motion-reduce:transition-none"
                />
              </div>
            )}
            {job.error && (
              <p className="text-sm text-destructive">{job.error}</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
