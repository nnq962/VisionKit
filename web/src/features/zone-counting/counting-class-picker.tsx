import { useState } from "react";
import { SearchIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function CountingClassPicker({
  names,
  selected,
  onChange,
}: {
  names: string[];
  selected: string[];
  onChange: (classes: string[]) => void;
}) {
  const [search, setSearch] = useState("");
  const filtered = names.filter((name) =>
    name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
  );
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground tabular-nums">
          {selected.length} / {names.length} đã chọn
        </span>
        <div className="flex flex-wrap gap-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onChange(names)}
          >
            Chọn tất cả
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => onChange([])}
          >
            Bỏ chọn
          </Button>
        </div>
      </div>
      <div className="relative">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          aria-label="Tìm class cần đếm"
          placeholder="Tìm class…"
          className="pl-9"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>
      <div
        className="grid max-h-64 grid-cols-2 gap-1 overflow-y-auto rounded-lg border p-2"
        role="group"
        aria-label="Class có sẵn của model"
      >
        {filtered.map((name) => (
          <label
            key={name}
            className="flex min-w-0 cursor-pointer items-center gap-2 rounded p-2 text-sm hover:bg-muted/50"
          >
            <input
              type="checkbox"
              className="size-4 shrink-0 accent-primary"
              checked={selected.includes(name)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...selected, name]
                    : selected.filter((item) => item !== name),
                )
              }
            />
            <span className="min-w-0 break-words">{name}</span>
          </label>
        ))}
        {!filtered.length && (
          <p className="col-span-2 p-3 text-xs text-muted-foreground">
            Không tìm thấy class.
          </p>
        )}
      </div>
    </div>
  );
}
