import { PlayIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { YoloParameters } from "../types";

export function RunStep({
  source,
  model,
  parameters,
}: {
  source: string;
  model: string;
  parameters: YoloParameters;
}) {
  const { confidence, iou, imageSize, device } = parameters;
  return (
    <div className="max-w-xl space-y-6">
      <dl className="divide-y text-sm">
        {[
          ["Source", source],
          ["Model", model],
          ["Confidence / IoU", `${confidence} / ${iou}`],
          ["Image size", `${imageSize} px`],
          ["Thiết bị", device],
        ].map(([label, value]) => (
          <div
            key={label}
            className="grid grid-cols-[8rem_1fr] gap-4 py-3 first:pt-0"
          >
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="break-all font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <p id="run-status" className="rounded-lg bg-muted p-4 text-sm leading-6">
        Cấu hình đã sẵn sàng. Chức năng chạy YOLO sẽ khả dụng sau khi kết nối
        backend inference.
      </p>
      <Button disabled aria-describedby="run-status">
        <PlayIcon data-icon="inline-start" />
        Chạy pipeline
      </Button>
    </div>
  );
}
