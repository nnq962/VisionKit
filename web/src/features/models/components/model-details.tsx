import { ModelMetadataPanel, ModelMetadataStatus } from "./model-metadata";
import type { ModelSelection } from "../use-model-selection";
import { BoxIcon, CheckIcon } from "lucide-react";
import { formatBytes } from "@/features/sources/media-metadata";
import { modelTaskLabel } from "../catalog";
import type { StoredModel } from "../api";
import type { ModelDraft } from "../model-draft-storage";
import { DetailDisclosure } from "@/components/detail-disclosure";

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
  return (
    <aside
      aria-label="Thông tin model"
      className={`min-w-0 ${compact ? "space-y-4" : "space-y-6"} border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6`}
    >
      <h3 className="text-sm font-semibold">Thông tin model</h3>
      {title ? (
        <>
          <div className="space-y-2">
            <p className={`${compact ? "truncate" : "break-all"} text-sm font-medium`} title={title}>{title}</p>
            {compact && model && <p className="text-xs text-muted-foreground">{modelTaskLabel(model.task)} · {(model.format ?? "pt").toUpperCase()} · {formatBytes(model.sizeBytes)}</p>}
            {(!compact || file || model?.expiresAt) && <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {!file && <CheckIcon className="size-3.5" />}
              {file
                ? "Đang chuẩn bị model"
                : model?.expiresAt
                  ? "Model tạm · Chưa lưu thư viện"
                  : "Đã lưu trong thư viện"}
            </p>}
            {model && selection && (
              <ModelMetadataStatus model={model} selection={selection} />
            )}
          </div>
          <DetailDisclosure enabled={compact} title="Chi tiết model" open={Boolean(model && ["needs_input", "failed", "unavailable", "manual"].includes(model.inspection.status))}>
          <div className={`space-y-0 ${compact ? "mt-3 max-h-80 overflow-y-auto overscroll-contain pr-1 [scrollbar-width:thin]" : ""}`}>
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
          </DetailDisclosure>
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
