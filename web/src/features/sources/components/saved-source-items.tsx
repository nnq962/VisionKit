import type { ReactNode } from "react";
import { CameraIcon, CheckIcon, FileImageIcon, FilmIcon } from "lucide-react";
import { sourceKinds, sourceLabel, type VisionSource } from "../types";

/** Cùng bố cục nhóm và hàng source cho pipeline và Zone Counting. */
export function SavedSourceItems({
  items,
  selectedId,
  disabled = false,
  onSelect,
  renderActions,
}: {
  items: VisionSource[];
  selectedId?: string;
  disabled?: boolean;
  onSelect: (source: VisionSource) => void;
  renderActions?: (source: VisionSource) => ReactNode;
}) {
  const groups = sourceKinds
    .map((category) => ({
      ...category,
      items: items.filter((item) => item.kind === category.value),
    }))
    .filter((group) => group.items.length);
  return (
    <div className="space-y-5" aria-label="Source đã lưu">
      {groups.map((group) => (
        <section
          key={group.value}
          aria-label={group.label}
          className="space-y-2"
        >
          <h4 className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
            <span>{group.label}</span>
            <span className="tabular-nums">{group.items.length}</span>
          </h4>
          <div className="divide-y">
            {group.items.map((item) => {
              const Icon =
                item.kind === "image" || item.kind === "screen"
                  ? FileImageIcon
                  : item.kind === "video" || item.kind === "youtube"
                    ? FilmIcon
                    : CameraIcon;
              const active = selectedId === item.id;
              return (
                <div key={item.id}>
                  <button
                    type="button"
                    disabled={disabled}
                    aria-pressed={active}
                    onClick={() => onSelect(item)}
                    className={`flex w-full min-w-0 items-center gap-3 rounded-lg p-3 text-left transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring ${active ? "bg-accent text-accent-foreground" : "hover:bg-muted"}`}
                  >
                    <Icon className="size-5 shrink-0" />
                    <span className="min-w-0 flex-1 space-y-1">
                      <span className="block truncate text-sm font-medium">
                        {item.name}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {sourceLabel(item.kind)} ·{" "}
                        {item.kind === "stream"
                          ? item.location
                          : "Đã lưu trên máy"}
                      </span>
                    </span>
                    {active && <CheckIcon className="size-4 shrink-0" />}
                  </button>
                  {active && renderActions?.(item)}
                </div>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
