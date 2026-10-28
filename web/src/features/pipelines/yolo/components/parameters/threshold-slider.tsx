import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Slider dùng chuột/phím, ô số giữ khả năng nhập ngưỡng chính xác. */
export function ThresholdSlider({ id, label, hint, value, onChange }: {
  id: string;
  label: string;
  hint: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const numeric = Number(value);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={id}>{label}</Label>
        <Input
          aria-label={`${label} chính xác`}
          className="h-8 w-20 text-right tabular-nums"
          type="number" min="0" max="1" step="0.01" inputMode="decimal"
          value={value} onChange={(event) => onChange(event.target.value)}
        />
      </div>
      <input
        id={id} type="range" min="0" max="1" step="0.01"
        value={Number.isFinite(numeric) ? Math.min(1, Math.max(0, numeric)) : 0}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={`${id}-hint`}
        className="block h-8 w-full cursor-pointer accent-primary focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      />
      <p id={`${id}-hint`} className="text-xs leading-5 text-muted-foreground">{hint}</p>
    </div>
  );
}
