import { useEffect, useRef, useState } from "react";
import { SearchIcon } from "lucide-react";
import { SavedSourceItems } from "./saved-source-items";
import { Button } from "@/components/ui/button";
import { SavedSourceActions } from "./saved-source-actions";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SourceSelection } from "../use-source-selection";
import { useSourceLibrary } from "../use-source-library";
import { type SourceKind } from "../types";

export function SavedSourceList({ selection }: { selection: SourceSelection }) {
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState<SourceKind | "all">("all");
  const library = useSourceLibrary();
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
  const items = library.library;
  const categories: { value: SourceKind | "all"; label: string }[] = [
    { value: "all", label: "Tất cả" },
    { value: "image", label: "Ảnh" },
    { value: "video", label: "Video" },
    { value: "stream", label: "Camera RTSP" },
    { value: "screen", label: "Ảnh màn hình" },
  ];

  return (
    <div className="space-y-6">
      <div
        className="flex flex-wrap gap-1.5"
        role="group"
        aria-label="Phân loại source đã lưu"
      >
        {categories.map((category) => (
          <Button
            key={category.value}
            size="sm"
            variant={kind === category.value ? "secondary" : "ghost"}
            aria-pressed={kind === category.value}
            onClick={() => {
              setKind(category.value);
              library.filterLibrary({
                kind: category.value === "all" ? undefined : category.value,
                q: search.trim(),
              });
            }}
          >
            {category.label}
          </Button>
        ))}
      </div>
      <div className="space-y-2">
        <Label htmlFor="source-search">Tìm source đã lưu</Label>
        <div className="relative">
          <SearchIcon className="absolute top-2.5 left-3 size-4 text-muted-foreground" />
          <Input
            id="source-search"
            className="h-9 pl-9"
            maxLength={120}
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              library.filterLibrary({
                kind: kind === "all" ? undefined : kind,
                q: event.target.value.trim(),
              });
            }}
            placeholder="Tìm theo tên source…"
          />
        </div>
      </div>
      <SavedSourceItems
        items={items}
        selectedId={selection.source?.id}
        disabled={selection.saving}
        onSelect={selection.select}
        renderActions={(source) => (
          <SavedSourceActions source={source} selection={selection} />
        )}
      />
      <div>
        {!items.length && !library.libraryLoading && !library.libraryError && (
          <p className="py-10 text-center text-sm text-muted-foreground">
            {search
              ? "Không tìm thấy source. Thử tên khác."
              : kind !== "all"
                ? "Chưa có source thuộc loại này."
                : "Chưa có source đã lưu. Thêm source mới để bắt đầu."}
          </p>
        )}
      </div>
      {library.libraryLoading && (
        <p role="status" className="text-sm text-muted-foreground">
          Đang tải thư viện…
        </p>
      )}
      {library.libraryError && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-destructive">
            {library.libraryError}
          </p>
          <Button
            variant="outline"
            onClick={() => void library.refreshLibrary()}
          >
            Thử lại
          </Button>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-xs text-muted-foreground">
          Đã tải {library.library.length}/{library.libraryTotal} source.
        </p>
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
        <Button
          variant="ghost"
          size="sm"
          disabled={library.libraryLoading || selection.saving}
          onClick={() => void library.refreshLibrary()}
        >
          Làm mới
        </Button>
      </div>
    </div>
  );
}
