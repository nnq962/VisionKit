import { ChevronDownIcon, RotateCcwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { StoredModel } from "@/features/models/api";
import type { VisionSource } from "@/features/sources/types";
import { ClassFilter } from "../components/parameters/class-filter";
import { ParameterContext } from "../components/parameters/parameter-context";
import {
  deviceLabels,
  fixedImageSize,
  imageSizeLabel,
  isTemporalSource,
  modelImageSize,
  parametersForModel,
} from "../parameters";
import type { YoloParameters } from "../types";

export function ParametersStep({
  parameters,
  onChange,
  source,
  model,
  storageError,
}: {
  parameters: YoloParameters;
  onChange: (value: YoloParameters) => void;
  source: VisionSource | null;
  model: StoredModel | null;
  storageError?: string;
}) {
  const fixed = fixedImageSize(model);
  const classify = model?.task === "classify";
  const stride = model?.inspection.metadata?.stride ?? 32;
  const sizes = Array.from(
    new Set([
      "320",
      "480",
      "640",
      "960",
      "1280",
      modelImageSize(model),
      parameters.imageSize,
    ]),
  ).filter(
    (size) =>
      size === fixed ||
      size.split("x").every((value) => Number(value) % stride === 0),
  );
  const patch = (value: Partial<YoloParameters>) =>
    onChange({ ...parameters, ...value });
  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="min-w-0 space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Thiết lập nhận diện</h3>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onChange(parametersForModel(model))}
          >
            <RotateCcwIcon />
            Đặt lại
          </Button>
        </div>
        {classify ? (
          <p className="text-sm text-muted-foreground">
            Model Classification dùng toàn bộ class; không áp dụng ngưỡng bbox
            và NMS.
          </p>
        ) : (
          <div className="grid gap-6 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="confidence">Confidence</Label>
              <Input
                id="confidence"
                type="number"
                inputMode="decimal"
                min="0"
                max="1"
                step="0.01"
                value={parameters.confidence}
                onChange={(event) => patch({ confidence: event.target.value })}
                aria-describedby="confidence-hint"
              />
              <p
                id="confidence-hint"
                className="text-xs leading-5 text-muted-foreground"
              >
                Ngưỡng tin cậy tối thiểu · 0–1.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="iou">IoU / NMS</Label>
              <Input
                id="iou"
                type="number"
                inputMode="decimal"
                min="0"
                max="1"
                step="0.05"
                value={parameters.iou}
                onChange={(event) => patch({ iou: event.target.value })}
                aria-describedby="iou-hint"
              />
              <p
                id="iou-hint"
                className="text-xs leading-5 text-muted-foreground"
              >
                Lọc bbox trùng khi model dùng NMS.
              </p>
            </div>
          </div>
        )}
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="image-size">Kích thước đầu vào</Label>
            <Select
              value={parameters.imageSize}
              onValueChange={(imageSize) => patch({ imageSize })}
              disabled={Boolean(fixed)}
            >
              <SelectTrigger
                id="image-size"
                className="w-full"
                aria-describedby="image-size-hint"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {sizes.map((size) => (
                    <SelectItem key={size} value={size}>
                      {imageSizeLabel(size)}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <p
              id="image-size-hint"
              className="text-xs leading-5 text-muted-foreground"
            >
              {fixed
                ? "Cố định theo input của model ONNX."
                : "Kích thước xử lý, không đổi file gốc."}
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="device">Thiết bị chạy</Label>
            <Select
              value={parameters.device}
              onValueChange={(device) => patch({ device })}
            >
              <SelectTrigger
                id="device"
                className="w-full"
                aria-describedby="device-hint"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {Object.entries(deviceLabels).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <p
              id="device-hint"
              className="text-xs leading-5 text-muted-foreground"
            >
              Thiết bị sẽ được xác minh trước khi chạy.
            </p>
          </div>
        </div>
        {source?.kind === "stream" && (
          <div className="grid gap-6 border-t pt-6 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="live-fps">Giới hạn AI (FPS)</Label>
              <Input id="live-fps" type="number" min="1" max="60" value={parameters.liveFps} onChange={(event) => patch({ liveFps: event.target.value })} />
              <p className="text-xs leading-5 text-muted-foreground">Lấy frame mới nhất, bỏ frame cũ khi AI xử lý chậm.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="live-minutes">Giới hạn chạy (phút)</Label>
              <Input id="live-minutes" type="number" min="1" max="240" step="1" value={parameters.liveMinutes} onChange={(event) => patch({ liveMinutes: event.target.value })} />
              <p className="text-xs leading-5 text-muted-foreground">Tiếp tục khi chuyển trang; dừng khi hết hạn hoặc bấm Dừng AI.</p>
            </div>
          </div>
        )}
        {!classify && (
          <ClassFilter
            names={model?.inspection.metadata?.names ?? {}}
            parameters={parameters}
            onChange={onChange}
          />
        )}
        {!classify && (
          <details className="group border-t pt-6">
            <summary className="flex cursor-pointer list-none items-center justify-between rounded-sm text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
              Nâng cao
              <ChevronDownIcon className="size-4 text-muted-foreground transition-transform group-open:rotate-180 motion-reduce:transition-none" />
            </summary>
            <div className="space-y-6 pt-6">
              <div className="grid gap-6 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="max-det">Số kết quả tối đa / ảnh</Label>
                  <Input
                    id="max-det"
                    type="number"
                    min="1"
                    max="3000"
                    step="1"
                    value={parameters.maxDet}
                    onChange={(event) => patch({ maxDet: event.target.value })}
                  />
                </div>
                {isTemporalSource(source) && (
                  <div className="space-y-2">
                    <Label htmlFor="vid-stride">Bước lấy frame</Label>
                    <Input
                      id="vid-stride"
                      type="number"
                      min="1"
                      max="120"
                      step="1"
                      value={parameters.vidStride}
                      onChange={(event) =>
                        patch({ vidStride: event.target.value })
                      }
                      aria-describedby="stride-hint"
                    />
                    <p
                      id="stride-hint"
                      className="text-xs leading-5 text-muted-foreground"
                    >
                      1 = mọi frame; 2 = lấy mỗi 2 frame.
                    </p>
                  </div>
                )}
              </div>
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0 accent-primary"
                  checked={parameters.agnosticNms}
                  onChange={(event) =>
                    patch({ agnosticNms: event.target.checked })
                  }
                />
                <span className="space-y-1">
                  <span className="block text-sm font-medium">
                    NMS giữa các class
                  </span>
                  <span className="block text-xs leading-5 text-muted-foreground">
                    Lọc bbox trùng mà không phân biệt class, nếu model dùng NMS.
                  </span>
                </span>
              </label>
            </div>
          </details>
        )}
        {storageError && (
          <p role="status" className="text-xs text-destructive">
            {storageError}
          </p>
        )}
      </div>
      <ParameterContext source={source} model={model} parameters={parameters} />
    </div>
  );
}
