import { useState } from "react";
import { Dialog } from "radix-ui";
import { BoxIcon, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatBytes } from "@/features/sources/media-metadata";
import { modelTaskLabel } from "../catalog";
import type { StoredModel } from "../api";

function SavedModelRow({
  item,
  busy,
  onRemove,
}: {
  item: StoredModel;
  busy: boolean;
  onRemove: (id: string) => void;
}) {
  const [confirm, setConfirm] = useState(false);
  return (
    <li className="flex min-w-0 items-center gap-3 py-4">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted">
        <BoxIcon
          className="size-4 text-muted-foreground"
          strokeWidth={1.5}
          aria-hidden="true"
        />
      </span>
      <div className="min-w-0 flex-1 space-y-0.5">
        <p
          className="truncate text-sm font-medium"
          title={item.name ?? item.filename}
        >
          {item.name ?? item.filename}
        </p>
        <p
          className="truncate text-xs text-muted-foreground"
          title={`${item.familyName} · ${modelTaskLabel(item.task)} · ${(item.format ?? "pt").toUpperCase()}`}
        >
          {item.familyName} · {modelTaskLabel(item.task)} ·{" "}
          {(item.format ?? "pt").toUpperCase()}
          <span className="sm:hidden"> · {formatBytes(item.sizeBytes)}</span>
        </p>
      </div>
      <span className="hidden w-20 shrink-0 text-right text-xs tabular-nums text-muted-foreground sm:block">
        {formatBytes(item.sizeBytes)}
      </span>
      <Dialog.Root open={confirm} onOpenChange={setConfirm}>
        <Dialog.Trigger asChild>
          <Button
            size="icon-lg"
            variant="ghost"
            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            disabled={busy}
            aria-label={`Xoá ${item.filename}`}
            title="Xoá model"
          >
            <Trash2Icon />
          </Button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30" />
          <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-xl border bg-background p-4 shadow-lg md:p-6">
            <Dialog.Title className="text-base font-semibold">
              Xoá model?
            </Dialog.Title>
            <Dialog.Description className="break-words text-sm text-muted-foreground">
              Xoá {item.name ?? item.filename} và file đã lưu khỏi thư viện.
            </Dialog.Description>
            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <Button size="sm" variant="outline">
                  Huỷ
                </Button>
              </Dialog.Close>
              <Button
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => {
                  onRemove(item.id);
                  setConfirm(false);
                }}
              >
                Xác nhận xoá
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </li>
  );
}

export function SavedModelList({
  items,
  onRemove,
  onBrowse,
  filtered,
  onClearFilters,
  busy,
}: {
  items: StoredModel[];
  onRemove: (id: string) => void;
  onBrowse: () => void;
  filtered: boolean;
  onClearFilters?: () => void;
  busy: string[];
}) {
  if (!items.length)
    return (
      <div className="flex min-h-48 flex-col items-center justify-center gap-3 text-center">
        <BoxIcon className="size-7 text-muted-foreground" strokeWidth={1.5} />
        <p className="text-sm text-muted-foreground">
          {filtered ? "Không tìm thấy model" : "Chưa có model đã lưu"}
        </p>
        {filtered ? (
          onClearFilters && (
            <Button size="sm" variant="outline" onClick={onClearFilters}>
              Xoá bộ lọc
            </Button>
          )
        ) : (
          <Button size="sm" variant="outline" onClick={onBrowse}>
            Khám phá model
          </Button>
        )}
      </div>
    );
  return (
    <ul className="divide-y" aria-label="Model đã lưu">
      {items.map((item) => (
        <SavedModelRow
          key={item.id}
          item={item}
          busy={busy.includes(item.id)}
          onRemove={onRemove}
        />
      ))}
    </ul>
  );
}
