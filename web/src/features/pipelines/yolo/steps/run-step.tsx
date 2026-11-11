import type { Ref } from "react";
import {
  RunWorkspace,
  type RunNavigation,
} from "@/features/inference/components/run-workspace";
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
  onComplete,
  controlsTarget,
  navigationRef,
  onNavigate,
  onBusyChange,
  autoStart,
}: {
  source: string;
  model: string;
  parameters: YoloParameters;
  sourceKind?: SourceKind;
  modelRecord: StoredModel | null;
  sourceRecord: VisionSource | null;
  onComplete: () => Promise<void>;
  controlsTarget?: HTMLElement | null;
  navigationRef?: Ref<RunNavigation>;
  onNavigate: (step: number) => void;
  onBusyChange: (busy: boolean) => void;
  autoStart?: boolean;
}) {
  const classify = modelRecord?.task === "classify";
  const names = modelRecord?.inspection.metadata?.names ?? {};
  const rows = [
    ["Nguồn", source],
    ["Model", model],
    ...(!classify
      ? [["Confidence / IoU", `${parameters.confidence} / ${parameters.iou}`]]
      : []),
    ...(sourceKind && ["stream", "webcam"].includes(sourceKind)
      ? [
          ["Giới hạn AI", `${parameters.liveFps} FPS`],
          ["Giới hạn chạy", `${parameters.liveMinutes} phút`],
        ]
      : []),
    ["Kích thước đầu vào", imageSizeLabel(parameters.imageSize)],
    ["Thiết bị", deviceLabels[parameters.device]],
    [
      parameters.textPromptEnabled ? "Text prompt" : "Class",
      parameters.textPromptEnabled
        ? parameters.textPrompts
        : classify || parameters.classMode === "all"
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
    <RunWorkspace
      source={sourceRecord}
      model={modelRecord}
      parameters={parameters}
      onComplete={onComplete}
      controlsTarget={controlsTarget}
      navigationRef={navigationRef}
      onNavigate={onNavigate}
      onBusyChange={onBusyChange}
      autoStart={autoStart}
      configuration={
        <details className="border-t pt-4">
          <summary className="cursor-pointer text-xs font-medium">
            Cấu hình lượt chạy
          </summary>
          <div className="pt-4">
            <dl className="divide-y text-sm">
              {rows.map(([label, value]) => (
                <div key={label} className="space-y-1 py-2 first:pt-0">
                  <dt className="text-xs text-muted-foreground">{label}</dt>
                  <dd className="min-w-0 break-words font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </details>
      }
    />
  );
}
