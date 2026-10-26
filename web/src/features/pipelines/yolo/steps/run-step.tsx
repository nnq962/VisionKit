import { RunWorkspace } from "@/features/inference/components/run-workspace";
import type { VisionSource } from "@/features/sources/types";
import type { StoredModel } from "@/features/models/api";
import type { SourceKind } from "@/features/sources/types";
import { deviceLabels, imageSizeLabel } from "../parameters";
import type { YoloParameters } from "../types";

export function RunStep({
  source,
  model,
  parameters,
  sourceKind,
  modelRecord,
  sourceRecord,
}: {
  source: string;
  model: string;
  parameters: YoloParameters;
  sourceKind?: SourceKind;
  modelRecord: StoredModel | null;
  sourceRecord: VisionSource | null;
}) {
  const classify = modelRecord?.task === "classify";
  const names = modelRecord?.inspection.metadata?.names ?? {};
  const rows = [
    ["Source", source],
    ["Model", model],
    ...(!classify
      ? [["Confidence / IoU", `${parameters.confidence} / ${parameters.iou}`]]
      : []),
    ["Kích thước đầu vào", imageSizeLabel(parameters.imageSize)],
    ["Thiết bị", deviceLabels[parameters.device]],
    [
      "Class",
      classify || parameters.classMode === "all"
        ? "Tất cả class"
        : parameters.classes.map((id) => names[id] ?? id).join(", "),
    ],
    ...(!classify
      ? [
          ["Kết quả tối đa / ảnh", parameters.maxDet],
          ["NMS giữa các class", parameters.agnosticNms ? "Bật" : "Tắt"],
        ]
      : []),
    ...(sourceKind &&
    ["video", "stream", "webcam", "youtube"].includes(sourceKind)
      ? [["Bước lấy frame", parameters.vidStride]]
      : []),
  ];
  return (
    <div className="space-y-6">
      <RunWorkspace
        source={sourceRecord}
        model={modelRecord}
        parameters={parameters}
      />
      <details className="group border-t pt-6">
        <summary className="cursor-pointer text-sm font-semibold">
          Cấu hình lượt chạy
        </summary>
        <div className="pt-4">
          <dl className="divide-y text-sm">
            {rows.map(([label, value]) => (
              <div
                key={label}
                className="grid gap-2 py-3 first:pt-0 sm:grid-cols-[11rem_1fr] sm:gap-4"
              >
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="min-w-0 break-words font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </details>
    </div>
  );
}
