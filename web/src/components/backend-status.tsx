"use client";

import { useBackendStatus } from "@/hooks/use-backend-status";

const labels = {
  checking: "Đang kiểm tra",
  online: "Đã kết nối",
  offline: "Mất kết nối",
};
const colors = {
  checking: "bg-muted-foreground",
  online: "bg-success",
  offline: "bg-destructive",
};

export function BackendStatus() {
  const status = useBackendStatus();
  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      title={`Backend: ${labels[status]}`}
      className="ml-auto flex shrink-0 items-center gap-2 text-xs text-muted-foreground"
    >
      <span
        aria-hidden="true"
        className={`size-1.5 shrink-0 rounded-full ${colors[status]}`}
      />
      <span>
        <span className="sr-only sm:not-sr-only">
          Backend<span aria-hidden="true"> · </span>
        </span>
        {labels[status]}
      </span>
    </div>
  );
}
