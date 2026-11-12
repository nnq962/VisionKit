import { XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WorkspaceSection } from "@/components/workspace-page";
import { NewSourceForm } from "@/features/sources/components/new-source-form";
import { SourceDetails } from "@/features/sources/components/source-details";
import { SourceDraftNotice } from "@/features/sources/components/source-draft-notice";
import { SourceSaveForm } from "@/features/sources/components/source-save-form";
import type { SourceSelection } from "@/features/sources/use-source-selection";

export function SourceUploadPanel({
  selection,
  onClose,
}: {
  selection: SourceSelection;
  onClose: () => void;
}) {
  return (
    <WorkspaceSection
      title="Thêm nguồn"
      titleId="upload-heading"
      variant="plain"
      actions={
        <Button
          variant="ghost"
          size="icon-lg"
          disabled={selection.saving}
          onClick={onClose}
          aria-label="Đóng thêm nguồn"
        >
          <XIcon />
        </Button>
      }
    >
      <div className="space-y-6 pb-6">
        <SourceDraftNotice selection={selection} />
        {selection.draftsReady ? (
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <div className="min-w-0 space-y-6">
              <NewSourceForm
                selection={selection}
                allowedKinds={["image", "video", "stream"]}
              />
              {selection.kind === "stream" && selection.saveError && (
                <p role="alert" className="text-sm text-destructive">
                  {selection.saveError}
                </p>
              )}
              {selection.kind === "stream" && selection.notice && (
                <p role="status" className="text-sm text-success">
                  {selection.notice}
                </p>
              )}
            </div>
            <SourceDetails
              compact
              source={selection.source}
              emptyKind={selection.kind}
              footer={
                selection.kind !== "stream" ? (
                  <SourceSaveForm selection={selection} />
                ) : undefined
              }
            />
          </div>
        ) : (
          <p role="status" className="text-sm text-muted-foreground">
            Đang khôi phục bản nháp…
          </p>
        )}
      </div>
    </WorkspaceSection>
  );
}
