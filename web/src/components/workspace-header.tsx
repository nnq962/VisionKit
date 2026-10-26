"use client";

import { LogViewer } from "@/features/logs/log-viewer";
import { BackendStatus } from "@/components/backend-status";
import { usePathname } from "next/navigation";
import { isRouteActive, workspaceNavigation } from "@/lib/navigation";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";

export function WorkspaceHeader() {
  const pathname = usePathname();
  const current = workspaceNavigation.find((item) =>
    isRouteActive(pathname, item.href),
  );
  return (
    <header className="relative z-20 flex h-16 shrink-0 items-center gap-3 border-b bg-background px-4 md:rounded-t-xl md:px-6">
      <SidebarTrigger aria-label="Đóng hoặc mở thanh điều hướng" />
      <Separator
        orientation="vertical"
        className="data-vertical:h-4 data-vertical:self-auto"
      />
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="hidden text-sm text-muted-foreground sm:inline">
          Workspace
        </span>
        <span
          className="hidden text-muted-foreground sm:inline"
          aria-hidden="true"
        >
          /
        </span>
        <span className="truncate text-sm font-medium">
          {current?.title ?? "VisionKit"}
        </span>
      </div>
      <BackendStatus />
      <Separator orientation="vertical" className="data-vertical:h-4 data-vertical:self-auto" />
      <LogViewer />
    </header>
  );
}
