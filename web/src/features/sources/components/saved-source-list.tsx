import { useEffect, useRef, useState } from "react";
import {
  CameraIcon,
  CheckIcon,
  FileImageIcon,
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
import { SavedSourceMenu } from "./saved-source-menu";
import type { SourceSelection } from "../use-source-selection";
import { useSourceLibrary } from "../use-source-library";
import { type SourceKind, sourceLabel } from "../types";
import { formatBytes, formatDuration } from "../media-metadata";

export function SavedSourceList({ selection }: { selection: SourceSelection }) {
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<SourceKind | "all">("all");
  const library = useSourceLibrary(
    !selection.libraryLoading && !selection.libraryError
      ? { items: selection.library, total: selection.libraryTotal }
      : undefined,
  );
  const previousLibrary = useRef(selection.library);
  const refresh = useRef(library.refreshLibrary);
  useEffect(() => {
    refresh.current = library.refreshLibrary;
  });
  useEffect(() => {
    if (previousLibrary.current !== selection.library) {
      previousLibrary.current = selection.library;
      void refresh.current();
    }
  }, [selection.library]);
  const categories: { value: SourceKind | "all"; label: string }[] = [
    { value: "all", label: "Tất cả loại" },
    { value: "image", label: "Ảnh" },
    { value: "video", label: "Video" },
    { value: "stream", label: "Camera RTSP" },
    { value: "screen", label: "Ảnh màn hình" },
  ];

  function filter(value: string, type: SourceKind | "all") {
    setSearch(value);
    setKind(type);
    library.filterLibrary({
      kind: type === "all" ? undefined : type,
      q: value.trim(),
    });
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            id="source-search"
            aria-label="Tìm nguồn đã lưu"
            className="h-9 pl-8"
            maxLength={120}
            value={search}
            onChange={(event) => filter(event.target.value, kind)}
            placeholder="Tìm nguồn…"
          />
        </div>
        <Select
          value={kind}
          onValueChange={(value) => filter(search, value as SourceKind | "all")}
        >
          <SelectTrigger
            aria-label="Lọc loại nguồn"
            className="h-9 w-32 shrink-0"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {categories.map((category) => (
                <SelectItem key={category.value} value={category.value}>
                  {category.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <Button
          variant="ghost"
          size="icon-lg"
          aria-label="Làm mới nguồn"
          title="Làm mới"
          disabled={library.libraryLoading || selection.saving}
          onClick={() => void library.refreshLibrary()}
        >
          <RefreshCwIcon
            className={
              library.libraryLoading
                ? "animate-spin motion-reduce:animate-none"
                : ""
            }
          />
        </Button>
      </div>
      <LibraryList label="Nguồn đã lưu">
        <ul className="divide-y" aria-label="Danh sách nguồn">
          {library.library.map((item) => {
            const Icon = ["image", "screen"].includes(item.kind)
              ? FileImageIcon
              : ["video", "youtube"].includes(item.kind)
                ? FilmIcon
                : CameraIcon;
            const active = selection.source?.id === item.id;
            return (
              <li
                key={item.id}
                className={`flex min-w-0 items-center gap-1 pr-3 transition-colors ${active ? "bg-accent text-accent-foreground" : "hover:bg-muted/50"}`}
              >
                <button
                  type="button"
                  disabled={selection.saving}
                  aria-pressed={active}
                  onClick={() => selection.select(item)}
                  className="flex min-w-0 flex-1 items-center gap-3 px-3 py-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                >
                  <span
                    className={`flex size-9 shrink-0 items-center justify-center rounded-lg ${active ? "bg-primary/10 text-accent-foreground" : "bg-muted text-muted-foreground"}`}
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
                    <span className="block truncate text-xs tabular-nums text-muted-foreground">
                      {[
                        sourceLabel(item.kind),
                        item.width && item.height
                          ? `${item.width} × ${item.height}`
                          : null,
                        item.kind === "video" && item.duration
                          ? formatDuration(item.duration)
                          : item.size
                            ? formatBytes(item.size)
                            : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                  <span className="flex size-5 shrink-0 items-center justify-center">
                    {active && <CheckIcon className="size-4 text-accent-foreground" />}
                  </span>
                </button>
                <SavedSourceMenu source={item} selection={selection} />
              </li>
            );
          })}
        </ul>
        {!library.library.length &&
          !library.libraryLoading &&
          !library.libraryError && (
            <p className="px-3 py-10 text-center text-sm text-muted-foreground">
              {search ? "Không tìm thấy nguồn." : "Chưa có nguồn."}
            </p>
          )}
        {library.libraryLoading && (
          <p role="status" className="p-3 text-sm text-muted-foreground">
            Đang tải…
          </p>
        )}
        {library.libraryError && (
          <div className="space-y-2 p-3">
            <p role="alert" className="text-sm text-destructive">
              {library.libraryError}
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => void library.refreshLibrary()}
            >
              Thử lại
            </Button>
          </div>
        )}
      </LibraryList>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs tabular-nums text-muted-foreground">
          {library.library.length < library.libraryTotal
            ? `${library.library.length} / ${library.libraryTotal}`
            : library.libraryTotal}{" "}
          nguồn
        </span>
        <div className="flex items-center gap-2">
          {library.library.length < library.libraryTotal && (
            <Button
              variant="outline"
              size="sm"
              disabled={library.libraryLoading}
              onClick={() => void library.refreshLibrary(true)}
            >
              Tải thêm
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
