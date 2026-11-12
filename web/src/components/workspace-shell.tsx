"use client";

import type { ReactNode } from "react";
import { AppSidebar } from "./app-sidebar";
import { WorkspaceHeader } from "./workspace-header";
import { SidebarInset, SidebarProvider } from "./ui/sidebar";

export function WorkspaceShell({ children }: { children: ReactNode }) {
  return (
    <SidebarProvider className="min-h-dvh">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:p-3"
      >
        Đến nội dung chính
      </a>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <WorkspaceHeader />
        <div id="main-content" tabIndex={-1} className="flex-1 p-4 md:p-8">
          <div className="mx-auto w-full max-w-6xl">{children}</div>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}
