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
    ["Source", source?.name ?? "Chưa chọn"],
    ["Loại nguồn", source ? sourceLabel(source.kind) : "—"],
    ["Model", model?.name ?? model?.filename ?? "Chưa chọn"],
    ["Tác vụ", modelTaskLabel(model?.task ?? null)],
    ["Định dạng", model?.format?.toUpperCase() ?? "—"],
    [
      "Input trong metadata",
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
      className="min-w-0 space-y-6 border-t pt-6 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6"
    >
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Áp dụng cho</h3>
        <p className="text-xs text-muted-foreground">
          Kiểm tra source và model trước khi chạy.
        </p>
      </div>
      <dl className="divide-y text-sm">
        {rows.map(([label, value]) => (
          <div
            key={label}
            className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)] gap-4 py-3 first:pt-0"
          >
            <dt className="shrink-0 text-muted-foreground">{label}</dt>
            <dd className="min-w-0 break-words text-left font-medium">
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <div className="space-y-3 border-t pt-6">
        <h3 className="text-sm font-semibold">Cấu hình chạy</h3>
        <p className="text-sm">
          {imageSizeLabel(parameters.imageSize)} ·{" "}
          {deviceLabels[parameters.device]}
        </p>
        <p className="text-xs text-muted-foreground">
          {parameters.classMode === "all"
            ? "Toàn bộ class"
            : `${parameters.classes.length} class đã chọn`}
        </p>
      </div>
    </aside>
  );
}
