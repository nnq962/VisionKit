import { useRef, useState } from "react";
import { Dialog } from "radix-ui";
import { EllipsisIcon, PencilIcon, Settings2Icon, Trash2Icon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { VisionSource } from "../types";
import type { SourceSelection } from "../use-source-selection";
import { SavedSourceActions } from "./saved-source-actions";

export function SavedSourceMenu({ source, selection }: { source: VisionSource; selection: SourceSelection }) {
  const [mode, setMode] = useState<"rename" | "delete" | "configure" | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  return <>
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button ref={trigger} size="icon-sm" variant="ghost" disabled={selection.saving} aria-label={`Thao tác với ${source.name}`}><EllipsisIcon /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-36">
        <DropdownMenuItem onSelect={() => setMode("rename")}><PencilIcon />Đổi tên</DropdownMenuItem>
        {source.kind === "stream" && <DropdownMenuItem onSelect={() => setMode("configure")}><Settings2Icon />Sửa cấu hình</DropdownMenuItem>}
        <DropdownMenuItem variant="destructive" onSelect={() => setMode("delete")}><Trash2Icon />Xoá</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    <Dialog.Root open={mode !== null} onOpenChange={open => { if (!open && !selection.saving) setMode(null); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/30" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border bg-background p-4 shadow-lg md:p-6"
          onEscapeKeyDown={event => { if (selection.saving) event.preventDefault(); }}
          onPointerDownOutside={event => { if (selection.saving) event.preventDefault(); }}
          onCloseAutoFocus={event => { event.preventDefault(); trigger.current?.focus(); }}>
          <div className="mb-5 flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <Dialog.Title className="text-base font-semibold">{mode === "rename" ? "Đổi tên source" : mode === "delete" ? "Xoá source" : "Cấu hình camera"}</Dialog.Title>
              <Dialog.Description className="break-all text-sm text-muted-foreground">{source.name}</Dialog.Description>
            </div>
            <Dialog.Close asChild><Button variant="ghost" size="icon-sm" disabled={selection.saving} aria-label="Đóng"><XIcon /></Button></Dialog.Close>
          </div>
          {mode && <SavedSourceActions key={mode} source={source} selection={selection} initialMode={mode} onDone={() => setMode(null)} />}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  </>;
}
