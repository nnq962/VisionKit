import type { OverlayPreferences } from "../use-overlay-preferences";

export function OverlayControls({
  preferences,
  onChange,
  pose,
  canConnect,
  classify,
}: {
  preferences: OverlayPreferences;
  onChange: (next: OverlayPreferences) => void;
  pose: boolean;
  canConnect: boolean;
  classify: boolean;
}) {
  const rows: [keyof OverlayPreferences, string, boolean][] = [
    ["boxes", "Bounding box", classify],
    ["labels", "Tên class / confidence", classify || !preferences.boxes],
    ["keypoints", "Điểm khớp", !pose],
    ["skeleton", "Đường nối khớp", !pose || !canConnect],
  ];
  return (
    <section className="space-y-4" aria-labelledby="overlay-heading">
      <h3 id="overlay-heading" className="text-sm font-semibold">
        Hiển thị
      </h3>
      <div className="divide-y">
        {rows.map(([key, label, disabled]) => (
          <label
            key={key}
            className={`flex items-center justify-between gap-4 py-3 first:pt-0 ${disabled ? "text-muted-foreground" : "cursor-pointer"}`}
          >
            <span className="text-sm">{label}</span>
            <input
              type="checkbox"
              className="size-4 shrink-0 accent-primary"
              checked={!disabled && preferences[key]}
              disabled={disabled}
              onChange={(event) =>
                onChange({ ...preferences, [key]: event.target.checked })
              }
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
