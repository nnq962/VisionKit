import { useState } from "react";
import Link from "next/link";
import {
  BoxIcon,
  CheckIcon,
  RefreshCwIcon,
  SearchIcon,
  ArrowUpRightIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatBytes } from "@/features/sources/media-metadata";
import { modelTaskLabel } from "../catalog";
import type { ModelSelection } from "../use-model-selection";

export function ModelLibraryPicker({
  selection,
}: {
  selection: Pick<
    ModelSelection,
    | "library"
    | "selectedId"
    | "loading"
    | "libraryError"
    | "validating"
    | "refresh"
  > & {
    update: (next: { selectedId: string }) => void;
  };
}) {
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(20);
  const query = search.trim().toLocaleLowerCase("vi");
  const items = selection.library.filter((item) =>
    `${item.name ?? ""} ${item.filename} ${item.familyName} ${item.format ?? "pt"} ${modelTaskLabel(item.task)}`
      .toLocaleLowerCase("vi")
      .includes(query),
  );
  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground" />
          <Input
            className="pl-9"
            aria-label="Tìm model đã lưu"
            placeholder="Tìm model…"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setLimit(20);
            }}
          />
        </div>
        <Button
          variant="outline"
          size="icon"
          aria-label="Làm mới model"
          disabled={selection.loading}
          onClick={selection.refresh}
        >
          <RefreshCwIcon
            className={
              selection.loading ? "animate-spin motion-reduce:animate-none" : ""
            }
          />
        </Button>
      </div>
      {selection.libraryError ? (
        <div role="alert" className="space-y-3">
          <p className="text-sm text-destructive">{selection.libraryError}</p>
          <Button variant="outline" onClick={selection.refresh}>
            Thử lại
          </Button>
        </div>
      ) : selection.loading && !selection.library.length ? (
        <p
          role="status"
          className="py-10 text-center text-sm text-muted-foreground"
        >
          Đang tải model…
        </p>
      ) : items.length ? (
        <fieldset className="min-w-0">
          <legend className="sr-only">Chọn một model đã lưu</legend>
          <div className="divide-y">
            {items.slice(0, limit).map((item) => (
              <div key={item.id} className="py-1 first:pt-0 last:pb-0">
                <label
                  className={`flex cursor-pointer items-center gap-3 rounded-lg p-3 text-left focus-within:ring-2 focus-within:ring-ring ${selection.selectedId === item.id ? "bg-accent text-accent-foreground" : "hover:bg-muted/50"}`}
                >
                  <input
                    className="sr-only"
                    type="radio"
                    name="pipeline-model"
                    value={item.id}
                    checked={selection.selectedId === item.id}
                    onChange={() => selection.update({ selectedId: item.id })}
                    disabled={selection.validating}
                  />
                  <BoxIcon
                    className="size-5 shrink-0 text-muted-foreground"
                    strokeWidth={1.5}
                  />
                  <span className="min-w-0 flex-1 space-y-1">
                    <span
                      title={item.name ?? item.filename}
                      className="block truncate text-sm font-medium"
                    >
                      {item.name ?? item.filename}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {item.familyName} · {modelTaskLabel(item.task)} ·{" "}
                      {(item.format ?? "pt").toUpperCase()} ·{" "}
                      {formatBytes(item.sizeBytes)}
                    </span>
                  </span>
                  {selection.selectedId === item.id && (
                    <CheckIcon className="size-4 shrink-0" />
                  )}
                </label>
              </div>
            ))}
          </div>
        </fieldset>
      ) : (
        <div className="flex min-h-44 flex-col items-center justify-center gap-3 text-center">
          <BoxIcon className="size-7 text-muted-foreground" strokeWidth={1.5} />
          <p className="text-sm text-muted-foreground">
            {query ? "Không tìm thấy model" : "Chưa có model đã lưu"}
          </p>
          <Button variant="outline" asChild>
            <Link href="/models">
              Mở Model Hub
              <ArrowUpRightIcon />
            </Link>
          </Button>
        </div>
      )}
      {items.length > limit && (
        <Button
          variant="outline"
          onClick={() => setLimit((value) => value + 20)}
        >
          Xem thêm ({items.length - limit})
        </Button>
      )}
      {items.length > 0 && (
        <Link
          href="/models"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
        >
          Tải thêm từ Model Hub
          <ArrowUpRightIcon className="size-3" />
        </Link>
      )}
    </div>
  );
}
