import { ModelSelectionProvider } from "@/features/models/model-selection-provider";
import { SourceProvider } from "@/features/sources/source-provider";
import { AppSidebar } from "@/components/app-sidebar";
import { WorkspaceHeader } from "@/components/workspace-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SourceProvider>
      <ModelSelectionProvider>
        <SidebarProvider className="h-dvh min-h-0 overflow-hidden">
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:p-3"
          >
            Đến nội dung chính
          </a>
          <AppSidebar />
          <SidebarInset className="min-h-0 min-w-0 overflow-hidden">
            <WorkspaceHeader />
            <div
              id="main-content"
              tabIndex={-1}
              className="min-h-0 flex-1 overflow-y-auto p-4 [scrollbar-width:none] [-ms-overflow-style:none] md:p-8 [&::-webkit-scrollbar]:hidden"
            >
              <div className="mx-auto w-full max-w-6xl">{children}</div>
            </div>
          </SidebarInset>
        </SidebarProvider>
      </ModelSelectionProvider>
    </SourceProvider>
  );
}
