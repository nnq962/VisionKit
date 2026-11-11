import type { OverlayPreferences } from "../use-overlay-preferences";

export function OverlayControls({
  preferences,
  onChange,
  pose,
  segment,
  canConnect,
  classify,
}: {
  preferences: OverlayPreferences;
  onChange: (next: OverlayPreferences) => void;
  pose: boolean;
  segment: boolean;
  canConnect: boolean;
  classify: boolean;
}) {
  const rows: [keyof OverlayPreferences, string, boolean][] = [
    ["boxes", "Khung nhận diện", classify],
    ["segments", "Vùng phân đoạn", !segment],
    ["labels", "Tên và độ tin cậy", classify || !preferences.boxes],
    ["keypoints", "Điểm khớp", !pose],
    ["skeleton", "Đường nối khớp", !pose || !canConnect],
  ];
  const visibleRows = rows.filter(([key]) => {
    if (key === "boxes" || key === "labels") return !classify;
    if (key === "segments") return segment;
    return pose;
  });
  return (
    <section className="space-y-2" aria-labelledby="overlay-heading">
      <h3 id="overlay-heading" className="text-sm font-semibold">
        Hiển thị
      </h3>
      <div className="divide-y">
        {visibleRows.map(([key, label, disabled]) => (
          <label
            key={key}
            className={`flex items-center justify-between gap-3 py-2 ${disabled ? "text-muted-foreground" : "cursor-pointer"}`}
          >
            <span className="text-xs leading-5">{label}</span>
            <input
              type="checkbox"
              className="size-3.5 shrink-0 accent-primary"
              checked={!disabled && preferences[key]}
              disabled={disabled}
              onChange={(event) =>
                onChange({ ...preferences, [key]: event.target.checked })
              }
            />
          </label>
        ))}
      </div>
      {pose && !canConnect && (
        <p className="text-xs leading-5 text-muted-foreground">
          Đường nối hiện hỗ trợ COCO 17 khớp.
        </p>
      )}
      {classify && (
        <p className="text-xs leading-5 text-muted-foreground">
          Kết quả phân loại hiển thị ở phần thống kê.
        </p>
      )}
    </section>
  );
}
