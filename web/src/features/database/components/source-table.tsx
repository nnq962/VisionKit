import { ChevronRightIcon, FolderOpenIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatBytes, formatDuration } from "@/features/sources/media-metadata";
import { sourceLabel, type VisionSource } from "@/features/sources/types";
import { SourceThumbnail } from "./source-thumbnail";

export function SourceTable({
  items,
  loading,
  filtered,
  onOpen,
  onAdd,
}: {
  items: VisionSource[];
  loading: boolean;
  filtered: boolean;
  onOpen: (source: VisionSource) => void;
  onAdd: () => void;
}) {
  if (loading)
    return (
      <div
        role="status"
        aria-label="Đang tải source"
        className="space-y-4 py-4"
      >
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  if (!items.length)
    return (
      <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
        <FolderOpenIcon
          className="size-8 text-muted-foreground"
          strokeWidth={1.5}
        />
        <p className="text-sm font-medium">
          {filtered ? "Không tìm thấy source" : "Chưa có source"}
        </p>
        {!filtered && (
          <Button variant="outline" onClick={onAdd}>
            Thêm source
          </Button>
        )}
      </div>
    );
  return (
    <div>
      <div
        className="hidden grid-cols-[minmax(0,1fr)_7rem_7rem_6rem_1rem] gap-4 border-b px-3 pb-3 text-xs text-muted-foreground md:grid"
        aria-hidden="true"
      >
        <span>Source</span>
        <span>Loại</span>
        <span>Dung lượng</span>
        <span>Ngày thêm</span>
        <span />
      </div>
      <ul className="divide-y" aria-label="Danh sách source">
        {items.map((source) => (
          <li key={source.id}>
            <button
              onClick={() => onOpen(source)}
              className="flex w-full items-center gap-3 rounded-lg px-2 py-4 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring md:grid md:grid-cols-[minmax(0,1fr)_7rem_7rem_6rem_1rem] md:gap-4 md:px-3"
            >
              <span className="flex min-w-0 flex-1 items-center gap-3">
                <SourceThumbnail source={source} />
                <span className="min-w-0 space-y-1">
                  <span className="block truncate text-sm font-medium">
                    {source.name}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {source.width && source.height
                      ? `${source.width} × ${source.height}`
                      : sourceLabel(source.kind)}
                    {source.kind === "video" && source.duration
                      ? ` · ${formatDuration(source.duration)}`
                      : ""}
                    <span className="md:hidden">
                      {" "}
                      · {formatBytes(source.size)}
                    </span>
                  </span>
                </span>
              </span>
              <span className="hidden text-sm text-muted-foreground md:block">
                {sourceLabel(source.kind)}
              </span>
              <span className="hidden text-sm tabular-nums text-muted-foreground md:block">
                {formatBytes(source.size)}
              </span>
              <span className="hidden text-xs tabular-nums text-muted-foreground md:block">
                {source.createdAt
                  ? new Date(source.createdAt).toLocaleDateString("vi-VN")
                  : "—"}
              </span>
              <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
