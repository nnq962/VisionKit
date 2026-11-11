"use client";

import type { ReactNode, Ref } from "react";
import { ScrollArea } from "radix-ui";

export function LibraryScrollArea({
  label,
  children,
  scrollRef,
}: {
  label: string;
  children: ReactNode;
  scrollRef?: Ref<HTMLDivElement>;
}) {
  return (
    <ScrollArea.Root type="auto" className="relative overflow-hidden rounded-lg border focus-within:ring-2 focus-within:ring-ring">
      <ScrollArea.Viewport
        ref={scrollRef}
        role="region"
        aria-label={label}
        tabIndex={0}
        disableImplicitContentElement
        className="max-h-[clamp(12rem,calc(100dvh-29rem),24rem)] min-h-32 w-full overscroll-contain outline-none"
      >
        <ScrollArea.Content className="pr-3" style={{ display: "block" }}>{children}</ScrollArea.Content>
      </ScrollArea.Viewport>
      <ScrollArea.Scrollbar orientation="vertical" className="flex w-2.5 touch-none p-0.5 select-none">
        <ScrollArea.Thumb className="relative flex-1 rounded-full bg-border hover:bg-muted-foreground/50" />
      </ScrollArea.Scrollbar>
    </ScrollArea.Root>
  );
}
