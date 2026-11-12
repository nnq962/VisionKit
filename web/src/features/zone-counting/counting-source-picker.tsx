import {
  CameraIcon,
  CheckIcon,
  FilmIcon,
  RefreshCwIcon,
  SearchIcon,
} from "lucide-react";
import { LibraryList } from "@/components/library-list";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatDuration } from "@/features/sources/media-metadata";
import type { VisionSource } from "@/features/sources/types";

export function CountingSourcePicker({
  items,
  total,
  selectedId,
  search,
  filter,
  loading,
  disabled,
  onSearch,
  onFilter,
  onRefresh,
  onSelect,
}: {
  items: VisionSource[];
  total: number;
  selectedId: string;
  search: string;
  filter: string;
  loading: boolean;
  disabled: boolean;
  onSearch: (value: string) => void;
  onFilter: (value: string) => void;
  onRefresh: () => void;
  onSelect: (source: VisionSource) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-32 flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Tìm nguồn đã lưu"
            className="h-9 pl-8"
            maxLength={120}
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Tìm nguồn…"
          />
        </div>
        <Select value={filter} onValueChange={onFilter}>
          <SelectTrigger
            aria-label="Lọc loại nguồn"
            className="h-9 w-32 shrink-0"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">Tất cả loại</SelectItem>
              <SelectItem value="video">Video</SelectItem>
              <SelectItem value="stream">Camera RTSP</SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
        <Button
          variant="ghost"
          size="icon-lg"
          aria-label="Làm mới nguồn"
          title="Làm mới"
          disabled={disabled || loading}
          onClick={onRefresh}
        >
          <RefreshCwIcon
            className={loading ? "animate-spin motion-reduce:animate-none" : ""}
          />
        </Button>
      </div>
      <LibraryList label="Nguồn đã lưu">
        <ul className="divide-y" aria-label="Danh sách nguồn">
          {items.map((item) => {
            const active = selectedId === item.id;
            const Icon = item.kind === "stream" ? CameraIcon : FilmIcon;
            return (
              <li
                key={item.id}
                className={
                  active
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-muted/50"
                }
              >
                <button
                  type="button"
                  aria-pressed={active}
                  disabled={disabled || loading}
                  onClick={() => onSelect(item)}
                  className="flex w-full min-w-0 items-center gap-3 px-3 py-3 text-left transition-colors outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:opacity-50"
                >
                  <span
                    className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${active ? "bg-primary/10" : "bg-muted text-muted-foreground"}`}
                  >
                    <Icon className="size-4" aria-hidden="true" />
                  </span>
                  <span className="min-w-0 flex-1 space-y-1">
                    <span
                      className="block truncate text-sm font-medium"
                      title={item.name}
                    >
                      {item.name}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground tabular-nums">
                      {[
                        item.kind === "stream" ? "Camera RTSP" : "Video",
                        item.width && item.height
                          ? `${item.width} × ${item.height}`
                          : null,
                        item.duration ? formatDuration(item.duration) : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                  <span className="flex size-5 shrink-0 items-center justify-center">
                    {active && <CheckIcon className="size-4" />}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {loading ? (
          <p role="status" className="p-3 text-sm text-muted-foreground">
            Đang tải nguồn…
          </p>
        ) : (
          !items.length && (
            <p className="px-3 py-10 text-center text-sm text-muted-foreground">
              {search
                ? "Không tìm thấy nguồn."
                : filter !== "all"
                  ? "Chưa có nguồn thuộc loại này."
                  : "Chưa có nguồn. Thêm nguồn mới để bắt đầu."}
            </p>
          )
        )}
      </LibraryList>
      <p className="text-xs text-muted-foreground tabular-nums">
        {items.length} / {total} nguồn
      </p>
    </div>
  );
}
