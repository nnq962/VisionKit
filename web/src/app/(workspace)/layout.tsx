import { ModelSelectionProvider } from "@/features/models/model-selection-provider";
import { SourceProvider } from "@/features/sources/source-provider";
import { WorkspaceShell } from "@/components/workspace-shell";

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <SourceProvider>
      <ModelSelectionProvider>
        <WorkspaceShell>{children}</WorkspaceShell>
      </ModelSelectionProvider>
    </SourceProvider>
  );
}
