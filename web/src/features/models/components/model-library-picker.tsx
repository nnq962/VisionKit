import { useState } from "react";
import { LibraryList } from "@/components/library-list";
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
    update: (next: { selectedId: string | null }) => void;
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
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            className="h-9 pl-9"
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
          variant="ghost"
          size="icon-lg"
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
      <LibraryList label="Model đã lưu">
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
                <label
                  key={item.id}
                  className={`flex min-w-0 cursor-pointer items-center gap-3 px-4 py-4 text-left transition-colors first:rounded-t-xl last:rounded-b-xl ${selection.selectedId === item.id ? "bg-primary/5" : "hover:bg-muted/50"}`}
                >
                  <span className="relative flex size-4 shrink-0">
                    <input
                      className="peer size-4 cursor-pointer appearance-none rounded border border-input bg-background checked:border-ring checked:bg-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
                      type="checkbox"
                      name="pipeline-model"
                      value={item.id}
                      checked={selection.selectedId === item.id}
                      onChange={(event) =>
                        selection.update({
                          selectedId: event.target.checked ? item.id : null,
                        })
                      }
                      disabled={selection.validating}
                    />
                    <CheckIcon
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-0 hidden size-4 text-primary-foreground peer-checked:block"
                      strokeWidth={2.5}
                    />
                  </span>
                  <span className="min-w-0 flex-1 space-y-1">
                    <span
                      title={item.name ?? item.filename}
                      className="block truncate text-sm font-medium"
                    >
                      {item.name ?? item.filename}
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {modelTaskLabel(item.task)} ·{" "}
                      {(item.format ?? "pt").toUpperCase()} ·{" "}
                      {formatBytes(item.sizeBytes)}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        ) : (
          <div className="flex min-h-44 flex-col items-center justify-center gap-3 text-center">
            <BoxIcon
              className="size-7 text-muted-foreground"
              strokeWidth={1.5}
            />
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
      </LibraryList>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="tabular-nums">
          {Math.min(items.length, limit)} / {items.length} model
        </span>
        {items.length > limit && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setLimit((value) => value + 20)}
          >
            Xem thêm
          </Button>
        )}
        {items.length > 0 && (
          <Link
            href="/models"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
          >
            Model Hub
            <ArrowUpRightIcon className="size-3" />
          </Link>
        )}
      </div>
    </div>
  );
}
