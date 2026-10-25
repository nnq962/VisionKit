import { ModelMetadataPanel } from "./model-metadata";
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
}: {
  model: StoredModel | null;
  draft?: ModelDraft;
  selection?: ModelSelection;
}) {
  const file = draft?.file;
  const title = file
    ? draft.name || file.name
    : (model?.name ?? model?.filename);
  const details = file
    ? [
        ["Tệp", file.name],
        ["Định dạng", file.name.split(".").pop()?.toUpperCase() ?? "—"],
        ["Dung lượng", formatBytes(file.size)],
      ]
    : model
      ? [
          ["Tệp", model.filename],
          ["Họ model", model.familyName],
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
      className="min-w-0 space-y-6 border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
    >
      <h3 className="text-sm font-semibold">Thông tin model</h3>
      {title ? (
        <>
          <div className="space-y-2">
            <p className="break-all text-sm font-medium">{title}</p>
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {!file && <CheckIcon className="size-3.5" />}
              {file ? "Bản nháp chưa lưu" : "Đã lưu trong thư viện"}
            </p>
          </div>
          <dl className="divide-y text-sm">
            {details.map(([label, value]) => (
              <div
                key={label}
                className="flex justify-between gap-4 py-3 first:pt-0"
              >
                <dt className="shrink-0 text-muted-foreground">{label}</dt>
                <dd
                  className="min-w-0 break-all text-right font-medium"
                  title={label === "SHA-256" ? model?.sha256 : undefined}
                >
                  {value}
                </dd>
              </div>
            ))}
          </dl>
          {file ? (
            <p className="text-xs leading-5 text-muted-foreground">
              Metadata sẽ được đọc sau khi lưu.
            </p>
          ) : model && selection ? (
            <ModelMetadataPanel
              key={model.id}
              model={model}
              selection={selection}
            />
          ) : null}
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
