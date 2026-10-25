import { useState } from "react";
import { ArrowUpRightIcon, CheckIcon, DownloadIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  modelVariant,
  sizeLabels,
  taskLabels,
  type ModelFamily,
  type ModelSize,
  type ModelTask,
  type ModelVariant,
} from "../catalog";
import type { ModelDownload, StoredModel } from "../api";

export function ModelCatalogRow({
  family,
  taskFilter,
  saved,
  jobs,
  ready,
  busy,
  onDownload,
  onCancel,
}: {
  family: ModelFamily;
  taskFilter: ModelTask | "all";
  saved: StoredModel[];
  jobs: Record<string, ModelDownload>;
  ready: boolean;
  busy: string[];
  onDownload: (variant: ModelVariant) => void;
  onCancel: (id: string) => void;
}) {
  const [size, setSize] = useState<ModelSize>(family.sizes[0]);
  const [task, setTask] = useState<ModelTask>(family.tasks[0]);
  const selectedTask = taskFilter === "all" ? task : taskFilter;
  const variant = modelVariant(family, selectedTask, size);
  const latest = jobs[variant.id];
  const job =
    latest && ["queued", "downloading"].includes(latest.status)
      ? latest
      : undefined;
  const installed = saved.some((item) => item.id === variant.id);
  return (
    <li className="py-6 first:pt-0 last:pb-0">
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] xl:gap-8">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold tracking-tight">
              {family.name}
            </h3>
            {family.openVocabulary && (
              <span className="rounded-md bg-accent px-2 py-0.5 text-xs text-accent-foreground">
                Open vocabulary
              </span>
            )}
            <a
              href={family.docs}
              target="_blank"
              rel="noreferrer"
              className="rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
              aria-label={`Tài liệu ${family.name}`}
            >
              <ArrowUpRightIcon className="size-4" />
            </a>
          </div>
          <p className="text-sm leading-6 text-muted-foreground">
            {family.description}
          </p>
          <p className="text-xs text-muted-foreground">
            Ultralytics · PyTorch .pt
          </p>
        </div>
        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={selectedTask}
              onValueChange={(value) => setTask(value as ModelTask)}
              disabled={taskFilter !== "all"}
            >
              <SelectTrigger
                className="w-40"
                aria-label={`Tác vụ ${family.name}`}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {family.tasks.map((item) => (
                    <SelectItem key={item} value={item}>
                      {taskLabels[item]}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <div
              className="flex gap-1"
              role="group"
              aria-label={`Kích cỡ ${family.name}`}
            >
              {family.sizes.map((item) => (
                <Button
                  key={item}
                  size="icon-sm"
                  variant={item === size ? "secondary" : "ghost"}
                  aria-pressed={item === size}
                  aria-label={`${family.name} ${sizeLabels[item]}`}
                  title={sizeLabels[item]}
                  onClick={() => setSize(item)}
                  className={
                    item === size ? "text-primary" : "text-muted-foreground"
                  }
                >
                  {item.toUpperCase()}
                </Button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="min-w-0 break-all text-xs text-muted-foreground">
              {variant.filename}
            </span>
            {job ? (
              <div className="flex items-center gap-2">
                <span
                  role="status"
                  className="text-xs tabular-nums text-muted-foreground"
                >
                  {job.status === "queued"
                    ? "Đang chờ"
                    : `Đang tải ${job.progress}%`}
                </span>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  disabled={busy.includes(variant.id)}
                  aria-label={`Huỷ tải ${variant.filename}`}
                  onClick={() => onCancel(variant.id)}
                >
                  <XIcon />
                </Button>
              </div>
            ) : (
              <Button
                variant={installed ? "secondary" : "outline"}
                size="sm"
                disabled={installed || !ready || busy.includes(variant.id)}
                onClick={() => onDownload(variant)}
                aria-label={`${installed ? "Đã lưu" : "Tải"} ${variant.filename}`}
              >
                {installed ? <CheckIcon /> : <DownloadIcon />}
                {installed
                  ? "Đã lưu"
                  : busy.includes(variant.id)
                    ? "Đang gửi…"
                    : latest?.status === "failed"
                      ? "Thử lại"
                      : "Tải về"}
              </Button>
            )}
          </div>
          {!job && latest?.status === "failed" && (
            <p className="text-xs text-destructive">{latest.error}</p>
          )}
          {job && (
            <div
              role="progressbar"
              aria-label={`Tiến độ ${variant.filename}`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={job.progress}
              className="h-1 overflow-hidden rounded bg-muted"
            >
              <div
                className="h-full bg-primary transition-[width] duration-200 motion-reduce:transition-none"
                style={{ width: `${job.progress}%` }}
              />
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
