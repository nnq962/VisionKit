import { useState } from "react";
import { SearchIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { YoloParameters } from "../../types";

export function ClassFilter({
  names,
  parameters,
  onChange,
}: {
  names: Record<string, string>;
  parameters: YoloParameters;
  onChange: (value: YoloParameters) => void;
}) {
  const [search, setSearch] = useState("");
  const entries = Object.entries(names);
  const filtered = entries.filter(([id, name]) =>
    `${id} ${name}`
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase()),
  );
  return (
    <section
      className="space-y-4 border-t pt-6"
      aria-labelledby="class-filter-heading"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="class-filter-heading" className="text-sm font-semibold">
          Lọc class
        </h3>
        <span className="text-xs text-muted-foreground tabular-nums">
          {parameters.classMode === "all"
            ? `${entries.length} class`
            : `${parameters.classes.length} đã chọn`}
        </span>
      </div>
      {entries.length ? (
        <>
          <div
            role="group"
            aria-label="Phạm vi class"
            className="flex flex-wrap gap-2"
          >
            <Button
              size="sm"
              variant={parameters.classMode === "all" ? "secondary" : "outline"}
              aria-pressed={parameters.classMode === "all"}
              onClick={() => onChange({ ...parameters, classMode: "all" })}
            >
              Tất cả class
            </Button>
            <Button
              size="sm"
              variant={
                parameters.classMode === "selected" ? "secondary" : "outline"
              }
              aria-pressed={parameters.classMode === "selected"}
              onClick={() => onChange({ ...parameters, classMode: "selected" })}
            >
              Chọn class
            </Button>
          </div>
          {parameters.classMode === "selected" && (
            <div className="space-y-3">
              <div className="relative">
                <SearchIcon className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground" />
                <Input
                  aria-label="Tìm class"
                  placeholder="Tìm theo tên hoặc ID…"
                  className="pl-9"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <fieldset className="grid max-h-56 grid-cols-2 gap-1 overflow-y-auto rounded-lg border p-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                <legend className="sr-only">Các class cần nhận diện</legend>
                {filtered.map(([id, name]) => (
                  <label
                    key={id}
                    className="flex min-w-0 cursor-pointer items-center gap-2 rounded p-2 text-sm hover:bg-muted/50"
                  >
                    <input
                      type="checkbox"
                      checked={parameters.classes.includes(id)}
                      onChange={(event) =>
                        onChange({
                          ...parameters,
                          classes: event.target.checked
                            ? [...parameters.classes, id]
                            : parameters.classes.filter(
                                (value) => value !== id,
                              ),
                        })
                      }
                      className="size-4 shrink-0 accent-primary"
                    />
                    <span className="min-w-0 break-words">
                      {name}
                      <span className="ml-1 text-xs text-muted-foreground">
                        {id}
                      </span>
                    </span>
                  </label>
                ))}
                {!filtered.length && (
                  <p className="col-span-2 p-3 text-sm text-muted-foreground">
                    Không tìm thấy class
                  </p>
                )}
              </fieldset>
            </div>
          )}
        </>
      ) : (
        <p className="text-xs text-muted-foreground">
          Model chưa có danh sách class. Dùng toàn bộ class khi chạy.
        </p>
      )}
    </section>
  );
}
