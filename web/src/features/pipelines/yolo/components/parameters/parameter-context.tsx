import { parseTextPrompts } from "../../text-prompts";
import type { StoredModel } from "@/features/models/api";
import { modelTaskLabel } from "@/features/models/catalog";
import { sourceLabel, type VisionSource } from "@/features/sources/types";
import { fixedImageSize, imageSizeLabel, deviceLabels } from "../../parameters";
import type { YoloParameters } from "../../types";

export function ParameterContext({
  source,
  model,
  parameters,
}: {
  source: VisionSource | null;
  model: StoredModel | null;
  parameters: YoloParameters;
}) {
  const rows = [
    ["Nguồn", source?.name ?? "Chưa chọn"],
    ["Loại nguồn", source ? sourceLabel(source.kind) : "—"],
    ["Model", model?.name ?? model?.filename ?? "Chưa chọn"],
    ["Tác vụ", modelTaskLabel(model?.task ?? null)],
    ["Định dạng", model?.format?.toUpperCase() ?? "—"],
    [
      "Kích thước model",
      fixedImageSize(model)
        ? imageSizeLabel(fixedImageSize(model)!)
        : model?.inspection.metadata?.imgsz?.length === 2
          ? model.inspection.metadata.imgsz.join(" × ")
          : model?.inspection.metadata?.input_shape?.length === 4
            ? model.inspection.metadata.input_shape
                .slice(2)
                .map((value) => value ?? "dynamic")
                .join(" × ")
            : "Chưa ghi nhận",
    ],
  ];
  return (
    <aside
      aria-label="Ngữ cảnh thông số"
      className="min-w-0 space-y-4 border-t pt-6 lg:sticky lg:top-0 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
    >
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Áp dụng cho</h3>
      </div>
      <dl className="space-y-3 text-sm">
        {rows.slice(0, 3).filter(([label]) => label !== "Loại nguồn").map(([label, value]) => (
          <div key={label} className="space-y-1">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="truncate font-medium" title={value}>{value}</dd>
          </div>
        ))}
      </dl>
      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer">Chi tiết đầu vào</summary>
        <dl className="divide-y pt-3">
          {rows.filter(([label]) => !["Nguồn", "Model"].includes(label)).map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3 py-2">
              <dt>{label}</dt><dd className="min-w-0 truncate text-foreground" title={value}>{value}</dd>
            </div>
          ))}
        </dl>
      </details>
      <div className="space-y-2 border-t pt-4">
        <h3 className="text-sm font-semibold">Cấu hình chạy</h3>
        <p className="text-sm">
          {imageSizeLabel(parameters.imageSize)} ·{" "}
          {deviceLabels[parameters.device]}
        </p>
        <p className="text-xs text-muted-foreground">
          {parameters.textPromptEnabled
            ? `${parseTextPrompts(parameters.textPrompts).length} vật thể theo text prompt`
            : parameters.classMode === "all"
            ? "Tất cả đối tượng"
            : `${parameters.classes.length} đối tượng đã chọn`}
        </p>
      </div>
    </aside>
  );
}
