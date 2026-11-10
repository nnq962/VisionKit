import { useEffect, useRef, useState } from "react";
import { CameraIcon, CheckIcon, FileImageIcon, FilmIcon, RefreshCwIcon, SearchIcon } from "lucide-react";
import { LibraryScrollArea } from "@/components/library-scroll-area";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SavedSourceActions } from "./saved-source-actions";
import type { SourceSelection } from "../use-source-selection";
import { useSourceLibrary } from "../use-source-library";
import { sourceKinds, type SourceKind, sourceLabel } from "../types";

export function SavedSourceList({ selection }: { selection: SourceSelection }) {
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<SourceKind | "all">("all");
  const library = useSourceLibrary();
  const scroll = useRef<HTMLDivElement>(null);
  const previousLibrary = useRef(selection.library);
  const refresh = useRef(library.refreshLibrary);
  useEffect(() => { refresh.current = library.refreshLibrary; });
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
  const groups = sourceKinds.map((category) => ({
    ...category, items: library.library.filter((item) => item.kind === category.value),
  })).filter((group) => group.items.length);

  function filter(value: string, type: SourceKind | "all") {
    setSearch(value);
    setKind(type);
    scroll.current?.scrollTo({ top: 0 });
    library.filterLibrary({ kind: type === "all" ? undefined : type, q: value.trim() });
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" />
          <Input id="source-search" aria-label="Tìm source đã lưu" className="pl-8" maxLength={120} value={search} onChange={(event) => filter(event.target.value, kind)} placeholder="Tìm source…" />
        </div>
        <Select value={kind} onValueChange={(value) => filter(search, value as SourceKind | "all")}>
          <SelectTrigger aria-label="Lọc loại source" className="w-32 shrink-0"><SelectValue /></SelectTrigger>
          <SelectContent><SelectGroup>{categories.map((category) => <SelectItem key={category.value} value={category.value}>{category.label}</SelectItem>)}</SelectGroup></SelectContent>
        </Select>
      </div>
      <LibraryScrollArea label="Source đã lưu" scrollRef={scroll}>
        {groups.map((group) => (
          <section key={group.value} aria-label={group.label}>
            <h4 className="sticky top-0 z-[1] flex items-center justify-between bg-background px-2 py-2 text-xs font-semibold text-muted-foreground">
              <span>{group.label}</span><span className="tabular-nums">{group.items.length}</span>
            </h4>
            <div className="divide-y">
              {group.items.map((item) => {
                const Icon = ["image", "screen"].includes(item.kind) ? FileImageIcon
                  : ["video", "youtube"].includes(item.kind) ? FilmIcon : CameraIcon;
                const active = selection.source?.id === item.id;
                return (
                  <div key={item.id}>
                    <button
                      type="button"
                      disabled={selection.saving}
                      aria-pressed={active}
                      onClick={() => selection.select(item)}
                      className={`flex w-full min-w-0 items-center gap-2.5 rounded-md px-2 py-2.5 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring ${active ? "bg-accent text-accent-foreground" : "hover:bg-muted"}`}
                    >
                      <Icon className="size-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 space-y-0.5">
                        <span className="block truncate text-sm font-medium" title={item.name}>{item.name}</span>
                        <span className="block truncate text-xs text-muted-foreground">
                          {item.width && item.height ? `${item.width} × ${item.height}` : sourceLabel(item.kind)}
                        </span>
                      </span>
                      {active && <CheckIcon className="size-4 shrink-0" />}
                    </button>
                    {active && (
                      <details className="px-2 pb-2 text-xs">
                        <summary className="cursor-pointer py-1 text-muted-foreground">Quản lý source</summary>
                        <SavedSourceActions source={item} selection={selection} />
                      </details>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        ))}
        {!library.library.length && !library.libraryLoading && !library.libraryError && (
          <p className="px-3 py-10 text-center text-sm text-muted-foreground">{search ? "Không tìm thấy source." : "Chưa có source."}</p>
        )}
        {library.libraryLoading && <p role="status" className="p-3 text-sm text-muted-foreground">Đang tải…</p>}
        {library.libraryError && (
          <div className="space-y-2 p-3">
            <p role="alert" className="text-sm text-destructive">{library.libraryError}</p>
            <Button size="sm" variant="outline" onClick={() => void library.refreshLibrary()}>Thử lại</Button>
          </div>
        )}
      </LibraryScrollArea>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs tabular-nums text-muted-foreground">{library.library.length} / {library.libraryTotal} source</span>
        <div className="flex gap-2">
          {library.library.length < library.libraryTotal && <Button variant="outline" size="sm" disabled={library.libraryLoading} onClick={() => void library.refreshLibrary(true)}>Tải thêm</Button>}
          <Button variant="ghost" size="icon-sm" aria-label="Làm mới source" title="Làm mới" disabled={library.libraryLoading || selection.saving} onClick={() => void library.refreshLibrary()}><RefreshCwIcon className={library.libraryLoading ? "animate-spin motion-reduce:animate-none" : ""} /></Button>
        </div>
      </div>
    </div>
  );
}
