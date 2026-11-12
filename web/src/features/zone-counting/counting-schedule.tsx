import { Clock3Icon, InfinityIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SourceKind } from "@/features/sources/types";

export function CountingSchedule({
  disabled,
  sourceKind,
  continuous,
  autoStart,
  fps,
  minutes,
  onContinuousChange,
  onAutoStartChange,
  onFpsChange,
  onMinutesChange,
}: {
  disabled: boolean;
  sourceKind: SourceKind;
  continuous: boolean;
  autoStart: boolean;
  fps: string;
  minutes: string;
  onContinuousChange: (value: boolean) => void;
  onAutoStartChange: (value: boolean) => void;
  onFpsChange: (value: string) => void;
  onMinutesChange: (value: string) => void;
}) {
  return (
    <fieldset
      disabled={disabled}
      className="min-w-0 space-y-5 rounded-xl border p-4 md:p-6"
    >
      <legend className="sr-only">Chế độ chạy</legend>
      <h3 className="text-sm font-semibold">Chế độ chạy</h3>
      <div className="space-y-2" role="radiogroup" aria-label="Chế độ chạy">
        {[
          {
            value: false,
            title: "Chạy một lượt",
            description:
              sourceKind === "stream"
                ? "Dừng sau thời lượng đã đặt."
                : "Xử lý hết video rồi dừng.",
            Icon: Clock3Icon,
          },
          {
            value: true,
            title: "Chạy liên tục 24/7",
            description:
              sourceKind === "stream"
                ? "Tự nối lượt và kết nối lại khi có lỗi."
                : "Tự lặp lại video và thử lại khi có lỗi.",
            Icon: InfinityIcon,
          },
        ].map(({ value, title, description, Icon }) => (
          <label
            key={title}
            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors ${continuous === value ? "border-primary bg-primary/5" : "hover:bg-muted/40"}`}
          >
            <input
              type="radio"
              name="counting-run-mode"
              className="mt-1 size-4 shrink-0 accent-primary"
              checked={continuous === value}
              onChange={() => onContinuousChange(value)}
            />
            <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <span className="space-y-1">
              <span className="block text-sm font-medium">{title}</span>
              <span className="block text-xs leading-5 text-muted-foreground">
                {description}
              </span>
            </span>
          </label>
        ))}
      </div>
      {sourceKind === "stream" && (
        <div className={`grid gap-4 ${continuous ? "" : "sm:grid-cols-2"}`}>
          <div className="space-y-2">
            <Label htmlFor="count-fps">Giới hạn AI (FPS)</Label>
            <Input
              id="count-fps"
              type="number"
              min="1"
              max="60"
              value={fps}
              onChange={(e) => onFpsChange(e.target.value)}
            />
          </div>
          {!continuous && (
            <div className="space-y-2">
              <Label htmlFor="count-minutes">Thời lượng (phút)</Label>
              <Input
                id="count-minutes"
                type="number"
                min="1"
                max="240"
                value={minutes}
                onChange={(e) => onMinutesChange(e.target.value)}
              />
            </div>
          )}
        </div>
      )}
      {continuous && (
        <div className="space-y-4 border-t pt-4">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              className="mt-1 size-4 shrink-0 accent-primary"
              checked={autoStart}
              onChange={(e) => onAutoStartChange(e.target.checked)}
            />
            <span>
              <span className="block text-sm font-medium">Tự khởi động</span>
              <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                Chạy ngay sau khi lưu và tiếp tục khi dịch vụ khởi động lại.
              </span>
            </span>
          </label>
          <p className="rounded-lg bg-muted/50 p-3 text-xs leading-5 text-muted-foreground">
            {autoStart
              ? "Lưu & chạy 24/7 để bắt đầu."
              : "Lưu cấu hình, sau đó bấm Bắt đầu tại Counting Monitor."}{" "}
            Chạy đến khi bấm Dừng. Cần máy và dịch vụ VisionKit luôn hoạt động.
          </p>
        </div>
      )}
    </fieldset>
  );
}
