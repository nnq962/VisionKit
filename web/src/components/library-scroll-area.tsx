import type { ReactNode, Ref } from "react";

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
    <div
      ref={scrollRef}
      role="region"
      aria-label={label}
      tabIndex={0}
      className="relative max-h-[clamp(12rem,calc(100dvh-29rem),24rem)] min-h-32 overflow-y-auto overscroll-contain rounded-lg border p-1 outline-none [scrollbar-gutter:stable] [scrollbar-width:thin] focus-visible:ring-2 focus-visible:ring-ring"
    >
      {children}
    </div>
  );
}
