import { useState } from "react";
import { LoaderCircleIcon, RefreshCwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { taskLabels, type ModelTask } from "../catalog";
import type { StoredModel } from "../api";
import type { ModelSelection } from "../use-model-selection";

const labels = {
  uninspected: "Chưa đọc metadata",
  queued: "Đang chờ đọc metadata",
  processing: "Đang đọc metadata…",
  ready: "Đã đọc metadata",
  needs_input: "Cần bổ sung thông tin",
  failed: "Không đọc được metadata",
  unavailable: "AI chưa kết nối",
  manual: "Đã khai báo thủ công",
};
export function ModelMetadataPanel({
  model,
  selection,
}: {
  model: StoredModel;
  selection: ModelSelection;
}) {
  const inspection = model.inspection;
  const metadata = inspection.metadata;
  const active = ["queued", "processing"].includes(inspection.status);
  const [showAll, setShowAll] = useState(false);
  const [manual, setManual] = useState(false);
  const [family, setFamily] = useState<"yolo" | "yoloe">(
    model.familyId.startsWith("yoloe") ? "yoloe" : "yolo",
  );
  const [task, setTask] = useState<ModelTask>(model.task ?? "detect");
  const names = Object.values(metadata?.names ?? {});
  const canConfigure = [
    "uninspected",
    "needs_input",
    "unavailable",
    "manual",
  ].includes(inspection.status);
  const rows = metadata
    ? [
        ...(metadata.class_count !== null
          ? [["Số class", String(metadata.class_count)]]
          : []),
        ...(metadata.imgsz
          ? [["Kích thước ảnh", metadata.imgsz.join(" × ")]]
          : []),
        ...(metadata.input_shape
          ? [
              [
                "Input shape",
                metadata.input_shape
                  .map((item) => item ?? "dynamic")
                  .join(" × "),
              ],
            ]
          : []),
        ...(metadata.stride ? [["Stride", String(metadata.stride)]] : []),
        ...(metadata.model_type ? [["Kiến trúc", metadata.model_type]] : []),
        ...(metadata.parameters
          ? [["Tham số", `${(metadata.parameters / 1e6).toFixed(2)} M`]]
          : []),
        ...(metadata.version ? [["Phiên bản", metadata.version]] : []),
      ]
    : [];
  return (
    <section
      className="space-y-4 border-t pt-6"
      aria-label="Metadata tự nhận diện"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p
          role="status"
          className={`flex items-center gap-2 text-xs ${inspection.status === "ready" ? "text-success" : inspection.status === "failed" ? "text-destructive" : "text-muted-foreground"}`}
        >
          {active && (
            <LoaderCircleIcon className="size-3.5 animate-spin motion-reduce:animate-none" />
          )}
          {labels[inspection.status]}
        </p>
        {!active && (
          <Button
            size="sm"
            variant="ghost"
            disabled={selection.inspecting}
            onClick={() => void selection.retryInspection()}
          >
            <RefreshCwIcon />
            {inspection.status === "ready" ? "Đọc lại" : "Thử đọc lại"}
          </Button>
        )}
      </div>
      {inspection.message && (
        <p className="text-xs leading-5 text-muted-foreground">
          {inspection.message}
        </p>
      )}
      {rows.length > 0 && (
        <dl className="divide-y text-sm">
          {rows.map(([label, value]) => (
            <div
              key={label}
              className="flex justify-between gap-4 py-3 first:pt-0"
            >
              <dt className="shrink-0 text-muted-foreground">{label}</dt>
              <dd className="min-w-0 break-all text-right font-medium">
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {names.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium">Classes</p>
          <div className="flex max-h-48 flex-wrap gap-1.5 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {(showAll ? names : names.slice(0, 8)).map((name, index) => (
              <span
                key={`${index}-${name}`}
                className="max-w-full break-words rounded bg-muted px-2 py-1 text-xs text-muted-foreground"
              >
                {name}
              </span>
            ))}
          </div>
          {names.length > 8 && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowAll(!showAll)}
            >
              {showAll ? "Thu gọn" : `Xem tất cả ${names.length} class`}
            </Button>
          )}
        </div>
      )}
      {canConfigure && !manual && (
        <Button size="sm" variant="outline" onClick={() => setManual(true)}>
          Khai báo thủ công
        </Button>
      )}
      {manual && canConfigure && (
        <form
          className="space-y-4"
          onSubmit={async (event) => {
            event.preventDefault();
            if (await selection.configure(family, task)) setManual(false);
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="model-manual-family">Họ model</Label>
            <Select
              value={family}
              onValueChange={(value: "yolo" | "yoloe") => {
                setFamily(value);
                if (value === "yoloe") setTask("segment");
              }}
            >
              <SelectTrigger id="model-manual-family" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="yolo">YOLO</SelectItem>
                  <SelectItem value="yoloe">YOLOE</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="model-manual-task">Tác vụ</Label>
            <Select
              value={task}
              onValueChange={(value) => setTask(value as ModelTask)}
              disabled={family === "yoloe"}
            >
              <SelectTrigger id="model-manual-task" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {Object.entries(taskLabels).map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2">
            <Button size="sm" disabled={selection.inspecting}>
              Lưu thông tin
            </Button>
            <Button
              size="sm"
              type="button"
              variant="outline"
              onClick={() => setManual(false)}
            >
              Huỷ
            </Button>
          </div>
        </form>
      )}
      {inspection.status === "ready" && (
        <p className="text-xs leading-5 text-muted-foreground">
          Metadata đã được đọc; chưa phải kết quả chạy inference.
        </p>
      )}
    </section>
  );
}
