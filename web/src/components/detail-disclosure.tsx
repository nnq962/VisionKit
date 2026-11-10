import type { ReactNode } from "react";

export function DetailDisclosure({
  enabled,
  title,
  open = false,
  children,
}: {
  enabled: boolean;
  title: string;
  open?: boolean;
  children: ReactNode;
}) {
  if (!enabled) return <>{children}</>;
  return (
    <details open={open}>
      <summary className="cursor-pointer text-xs text-muted-foreground">{title}</summary>
      {children}
    </details>
  );
}
