import { useState } from "react";
import { BoxIcon, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/features/sources/media-metadata";
import { sizeLabels, modelTaskLabel } from "../catalog";
import type { StoredModel } from "../api";

export function SavedModelList({
  items,
  onRemove,
  onBrowse,
  filtered,
  busy,
}: {
  items: StoredModel[];
  onRemove: (id: string) => void;
  onBrowse: () => void;
  filtered: boolean;
  busy: string[];
}) {
  const [confirm, setConfirm] = useState<string | null>(null);
  if (!items.length)
    return (
      <div className="flex min-h-56 flex-col items-center justify-center gap-3 text-center">
        <BoxIcon className="size-8 text-muted-foreground" strokeWidth={1.5} />
        <p className="text-sm font-medium">
          {filtered ? "Không tìm thấy model" : "Chưa có model đã lưu"}
        </p>
        {!filtered && (
          <Button variant="outline" onClick={onBrowse}>
            Khám phá model
          </Button>
        )}
      </div>
    );
  return (
    <ul className="divide-y" aria-label="Model đã lưu">
      {items.map((item) => (
        <li
          key={item.id}
          className="flex flex-wrap items-center justify-between gap-4 py-5 first:pt-0 last:pb-0"
        >
          <div className="min-w-0 space-y-1">
            <p className="break-all text-sm font-medium">
              {item.name ?? item.filename}
            </p>
            <p className="text-xs leading-5 text-muted-foreground">
              {item.familyName} · {modelTaskLabel(item.task)} ·{" "}
              {item.size ? `${sizeLabels[item.size]} · ` : ""}
              {formatBytes(item.sizeBytes)} · {item.format ?? "pt"}
            </p>
          </div>
          {confirm === item.id ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">
                Xoá model và file đã lưu?
              </span>
              <Button
                size="sm"
                variant="destructive"
                disabled={busy.includes(item.id)}
                onClick={() => {
                  onRemove(item.id);
                  setConfirm(null);
                }}
              >
                Xác nhận
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setConfirm(null)}
              >
                Huỷ
              </Button>
            </div>
          ) : (
            <Button
              size="icon-sm"
              variant="ghost"
              disabled={busy.includes(item.id)}
              aria-label={`Xoá ${item.filename}`}
              onClick={() => setConfirm(item.id)}
            >
              <Trash2Icon />
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}
