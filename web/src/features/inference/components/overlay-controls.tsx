import type { OverlayPreferences } from "../use-overlay-preferences";

export function OverlayControls({
  preferences,
  onChange,
  pose,
  segment,
  canConnect,
  classify,
  independentLabels = false,
  hideUnsupported = false,
  extraControls = [],
}: {
  preferences: OverlayPreferences;
  onChange: (next: OverlayPreferences) => void;
  pose: boolean;
  segment: boolean;
  canConnect: boolean;
  classify: boolean;
  independentLabels?: boolean;
  hideUnsupported?: boolean;
  extraControls?: {
    id: string;
    label: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
  }[];
}) {
  const rows: [keyof OverlayPreferences, string, boolean][] = [
    ["boxes", "Bounding box", classify],
    ["segments", "Segmentation", !segment],
    [
      "labels",
      "Tên class / confidence",
      classify || (!independentLabels && !preferences.boxes),
    ],
    ["keypoints", "Điểm khớp", !pose],
    ["skeleton", "Đường nối khớp", !pose || !canConnect],
  ];
  const controls = rows
    .filter(([key]) =>
      !hideUnsupported ||
      (key !== "keypoints" && key !== "skeleton" && (key !== "segments" || segment)),
    )
    .map(([key, label, disabled]) => ({
      id: key,
      label,
      disabled,
      checked: !disabled && preferences[key],
      onChange: (checked: boolean) => onChange({ ...preferences, [key]: checked }),
    }));
  const allControls = [
    ...controls,
    ...extraControls.map((control) => ({ ...control, disabled: false })),
  ];
  return (
    <section className="space-y-4" aria-labelledby="overlay-heading">
      <h3 id="overlay-heading" className="text-sm font-semibold">
        Hiển thị
      </h3>
      <div className="divide-y">
        {allControls.map(({ id, label, disabled, checked, onChange: change }) => (
          <label
            key={id}
            className={`flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0 ${disabled ? "text-muted-foreground" : "cursor-pointer"}`}
          >
            <span className="text-sm">{label}</span>
            <input
              type="checkbox"
              className="size-4 shrink-0 accent-primary"
              checked={checked}
              disabled={disabled}
              onChange={(event) => change(event.target.checked)}
            />
          </label>
        ))}
      </div>
      {pose && (
        <p className="text-xs leading-5 text-muted-foreground">
          {canConnect
            ? "Đường nối theo COCO 17 khớp."
            : "Đường nối hiện hỗ trợ COCO 17 khớp."}
        </p>
      )}
      {classify && (
        <p className="text-xs leading-5 text-muted-foreground">
          Model phân loại không có bbox hoặc keypoint.
        </p>
      )}
    </section>
  );
}
