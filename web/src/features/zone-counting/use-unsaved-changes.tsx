"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Dialog } from "radix-ui";
import { Button } from "@/components/ui/button";

type Confirmation = {
  title: string;
  description: string;
  label: string;
  action: () => void;
  discard?: boolean;
};

/** Giữ bản nháp khi chuyển cấu hình, theo liên kết hoặc đóng/tải lại trang. */
export function useUnsavedChanges(dirty: boolean, discard?: () => void) {
  const router = useRouter();
  const dirtyRef = useRef(dirty);
  const discardRef = useRef(discard);
  useEffect(() => {
    discardRef.current = discard;
  }, [discard]);
  const [pending, setPending] = useState<Confirmation | null>(null);
  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);
  const confirmDiscard = useCallback((action: () => void) => {
    if (!dirtyRef.current) {
      action();
      return;
    }
    setPending({
      title: "Bỏ thay đổi chưa lưu?",
      description:
        "Cấu hình hiện tại chưa được lưu. Thay đổi sẽ mất khi tiếp tục.",
      label: "Bỏ thay đổi",
      discard: true,
      action,
    });
  }, []);
  useEffect(() => {
    function beforeUnload(event: BeforeUnloadEvent) {
      if (!dirtyRef.current) return;
      event.preventDefault();
      event.returnValue = "";
    }
    function followLink(event: MouseEvent) {
      if (
        !dirtyRef.current ||
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const anchor = (event.target as Element).closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (
        !anchor ||
        anchor.target === "_blank" ||
        anchor.hasAttribute("download")
      )
        return;
      const url = new URL(anchor.href);
      if (
        url.origin === location.origin &&
        url.pathname === location.pathname &&
        url.search === location.search
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      confirmDiscard(() => {
        dirtyRef.current = false;
        if (url.origin === location.origin)
          router.push(url.pathname + url.search + url.hash);
        else location.assign(url.href);
      });
    }
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", followLink, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", followLink, true);
    };
  }, [confirmDiscard, router]);
  const dialog = (
    <Dialog.Root
      open={Boolean(pending)}
      onOpenChange={(open) => {
        if (!open) setPending(null);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 space-y-6 rounded-xl border bg-background p-6 shadow-xl">
          <div className="space-y-2">
            <Dialog.Title className="text-lg font-semibold">
              {pending?.title}
            </Dialog.Title>
            <Dialog.Description className="text-sm leading-6 text-muted-foreground">
              {pending?.description}
            </Dialog.Description>
          </div>
          <div className="flex flex-wrap justify-end gap-3">
            <Dialog.Close asChild>
              <Button variant="outline">Quay lại</Button>
            </Dialog.Close>
            <Button
              variant="destructive"
              onClick={() => {
                const action = pending?.action;
                if (pending?.discard) {
                  dirtyRef.current = false;
                  discardRef.current?.();
                }
                setPending(null);
                action?.();
              }}
            >
              {pending?.label}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
  return { confirmDiscard, ask: setPending, dialog };
}
