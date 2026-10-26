import { useState } from "react";
import {
  CameraIcon,
  CheckIcon,
  FileImageIcon,
  FilmIcon,
  SearchIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { SavedSourceActions } from "./saved-source-actions";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SourceSelection } from "../use-source-selection";
import { sourceLabel } from "../types";

export function SavedSourceList({ selection }: { selection: SourceSelection }) {
  const [search, setSearch] = useState("");
  const items = selection.library.filter((item) =>
    `${item.name} ${sourceLabel(item.kind)}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="source-search">Tìm source đã lưu</Label>
        <div className="relative">
          <SearchIcon className="absolute top-2.5 left-3 size-4 text-muted-foreground" />
          <Input
            id="source-search"
            className="h-9 pl-9"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Tên source hoặc loại dữ liệu…"
          />
        </div>
      </div>
      <div className="divide-y" aria-label="Source đã lưu">
        {items.map((item) => {
          const Icon =
            item.kind === "image"
              ? FileImageIcon
              : item.kind === "video"
                ? FilmIcon
                : CameraIcon;
          const active = selection.source?.id === item.id;
          return (
            <div key={item.id}>
              <button
                type="button"
                disabled={selection.saving}
                aria-pressed={active}
                onClick={() => selection.select(item)}
                className={`flex w-full min-w-0 items-center gap-3 rounded-lg p-3 text-left transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring ${active ? "bg-accent text-accent-foreground" : "hover:bg-muted"}`}
              >
                <Icon className="size-5 shrink-0" />
                <span className="min-w-0 flex-1 space-y-1">
                  <span className="block truncate text-sm font-medium">
                    {item.name}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {sourceLabel(item.kind)} · {item.kind === "stream" ? item.location : "Đã lưu trên máy"}
                  </span>
                </span>
                {active && <CheckIcon className="size-4 shrink-0" />}
              </button>
              {active && (
                <SavedSourceActions source={item} selection={selection} />
              )}
            </div>
          );
        })}
        {!items.length &&
          !selection.libraryLoading &&
          !selection.libraryError && (
            <p className="py-10 text-center text-sm text-muted-foreground">
              {search
                ? "Không tìm thấy source. Thử tên khác."
                : "Chưa có source đã lưu. Thêm source mới để bắt đầu."}
            </p>
          )}
      </div>
      {selection.libraryLoading && (
        <p role="status" className="text-sm text-muted-foreground">
          Đang tải thư viện…
        </p>
      )}
      {selection.libraryError && (
        <div className="space-y-2">
          <p role="alert" className="text-sm text-destructive">
            {selection.libraryError}
          </p>
          <Button
            variant="outline"
            onClick={() => void selection.refreshLibrary()}
          >
            Thử lại
          </Button>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-xs text-muted-foreground">
          Đã tải {selection.library.length}/{selection.libraryTotal} source.
        </p>
        {selection.library.length < selection.libraryTotal && (
          <Button
            variant="outline"
            size="sm"
            disabled={selection.libraryLoading}
            onClick={() => void selection.refreshLibrary(true)}
          >
            Tải thêm
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          disabled={selection.libraryLoading || selection.saving}
          onClick={() => void selection.refreshLibrary()}
        >
          Làm mới
        </Button>
      </div>
    </div>
  );
}
