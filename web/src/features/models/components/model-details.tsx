import { ModelMetadataPanel, ModelMetadataStatus } from "./model-metadata";
import type { ModelSelection } from "../use-model-selection";
import { BoxIcon, CheckIcon } from "lucide-react";
import { formatBytes } from "@/features/sources/media-metadata";
import { modelTaskLabel } from "../catalog";
import type { StoredModel } from "../api";
import type { ModelDraft } from "../model-draft-storage";

export function ModelDetails({
  model,
  draft,
  selection,
  compact = false,
}: {
  model: StoredModel | null;
  draft?: ModelDraft;
  compact?: boolean;
  selection?: Pick<
    ModelSelection,
    "inspecting" | "retryInspection" | "configure"
  >;
}) {
  const file = model ? null : draft?.file;
  const title = file
    ? draft?.name || file.name
    : (model?.name ?? model?.filename);
  const metadata = model?.inspection.metadata;
  const family =
    metadata?.family ??
    (model?.familyId.startsWith("yoloe")
      ? "yoloe"
      : model?.familyId.startsWith("yolo")
        ? "yolo"
        : null);
  const details = file
    ? [
        ["Tệp", file.name],
        ["Định dạng", file.name.split(".").pop()?.toUpperCase() ?? "—"],
        ["Dung lượng", formatBytes(file.size)],
      ]
    : model
      ? [
          ["Tệp", model.filename],
          [
            "Họ model",
            family === "yoloe"
              ? "YOLOE"
              : family === "yolo"
                ? "YOLO"
                : "Chưa xác định",
          ],
          ["Dòng model", metadata?.model_series ?? "Chưa xác định"],
          ["Biến thể", metadata?.scale ?? "Chưa xác định"],
          ["Tác vụ", modelTaskLabel(model.task)],
          ["Định dạng", (model.format ?? "pt").toUpperCase()],
          ["Dung lượng", formatBytes(model.sizeBytes)],
          ["Nguồn", model.origin === "upload" ? "Tải lên" : "Ultralytics"],
          ["SHA-256", model.sha256.slice(0, 12) + "…"],
        ]
      : [];
  if (compact) {
    const dimensions =
      metadata?.imgsz?.join(" × ") ||
      metadata?.input_shape
        ?.slice(-2)
        .map((value) => value ?? "Động")
        .join(" × ");
    const summary = model
      ? [
          ["Tác vụ", modelTaskLabel(model.task)],
          ["Họ model", family?.toUpperCase() ?? model.familyName],
          ["Định dạng", (model.format ?? "pt").toUpperCase()],
          ["Dung lượng", formatBytes(model.sizeBytes)],
          ["Đầu vào", dimensions || "Chưa xác định"],
          [
            "Số nhãn",
            String(
              metadata?.class_count ??
                (metadata?.names ? Object.keys(metadata.names).length : "—"),
            ),
          ],
          ...(metadata?.parameters
            ? [["Tham số", `${(metadata.parameters / 1e6).toFixed(2)} M`]]
            : []),
          ...(metadata?.model_type ? [["Kiến trúc", metadata.model_type]] : []),
        ]
      : details;
    return (
      <aside
        aria-label="Thông tin model"
        className="min-w-0 space-y-4 border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
      >
        <div className="space-y-1">
          <h3 className="break-words text-base font-semibold">
            {title || "Thông tin model"}
          </h3>
          {model && selection && (
            <ModelMetadataStatus model={model} selection={selection} compact />
          )}
          {file && (
            <p role="status" className="text-sm text-muted-foreground">
              Đang chuẩn bị model…
            </p>
          )}
          {model?.expiresAt && (
            <p className="text-xs text-muted-foreground">
              Model tạm · có thể chạy ngay hoặc lưu vào thư viện.
            </p>
          )}
        </div>
        {title ? (
          <>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-y py-3">
              {summary.map(([label, value]) => (
                <div key={label} className="min-w-0 space-y-1">
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="break-words text-sm font-medium">{value}</dd>
                </div>
              ))}
            </dl>
            {model && selection && (
              <ModelMetadataPanel
                key={model.id}
                model={model}
                selection={selection}
                compact
              />
            )}
          </>
        ) : (
          <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-muted-foreground">
            <BoxIcon className="size-8" strokeWidth={1.5} />
            <p className="text-sm">Chọn model để xem thông tin</p>
          </div>
        )}
      </aside>
    );
  }
  return (
    <aside
      aria-label="Thông tin model"
      className={`min-w-0 ${compact ? "space-y-4" : "space-y-6"} border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6`}
    >
      <h3 className="text-sm font-semibold">Thông tin model</h3>
      {title ? (
        <>
          <div className="space-y-2">
            <p
              className={`${compact ? "truncate" : "break-all"} text-sm font-medium`}
              title={title}
            >
              {title}
            </p>
            {compact && model && (
              <p className="text-xs text-muted-foreground">
                {modelTaskLabel(model.task)} ·{" "}
                {(model.format ?? "pt").toUpperCase()} ·{" "}
                {formatBytes(model.sizeBytes)}
              </p>
            )}
            {(!compact || file || model?.expiresAt) && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                {!file && <CheckIcon className="size-3.5" />}
                {file
                  ? "Đang chuẩn bị model"
                  : model?.expiresAt
                    ? "Model tạm · Chưa lưu thư viện"
                    : "Đã lưu trong thư viện"}
              </p>
            )}
            {model && selection && (
              <ModelMetadataStatus model={model} selection={selection} />
            )}
          </div>
          <div
            className={`space-y-0 ${compact ? "mt-3 max-h-80 overflow-y-auto overscroll-contain pr-1" : ""}`}
          >
            <dl className="divide-y text-sm">
              {details.map(([label, value]) => (
                <div
                  key={label}
                  className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)] gap-4 py-3 first:pt-0"
                >
                  <dt className="shrink-0 text-muted-foreground">{label}</dt>
                  <dd
                    className="min-w-0 break-all text-left font-medium"
                    title={label === "SHA-256" ? model?.sha256 : undefined}
                  >
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
            {file ? (
              <p className="text-xs leading-5 text-muted-foreground">
                Tự động đọc metadata sau khi tải lên.
              </p>
            ) : model && selection ? (
              <ModelMetadataPanel
                key={model.id}
                model={model}
                selection={selection}
              />
            ) : null}
          </div>
        </>
      ) : (
        <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-lg bg-muted/30 text-muted-foreground">
          <BoxIcon className="size-8" strokeWidth={1.5} />
          <p className="text-xs">Chưa chọn model</p>
        </div>
      )}
    </aside>
  );
}
