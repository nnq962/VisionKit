import type { ReactNode } from "react";

export function LibraryList({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div
      role="region"
      aria-label={label}
      className="overflow-hidden rounded-xl border"
    >
      {children}
    </div>
  );
}
