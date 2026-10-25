import { XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
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
    <section className="rounded-xl border" aria-labelledby="upload-heading">
      <div className="flex items-center justify-between border-b p-4 md:p-6">
        <h2
          id="upload-heading"
          tabIndex={-1}
          className="text-lg font-semibold outline-none"
        >
          Thêm source
        </h2>
        <Button
          variant="ghost"
          size="icon-sm"
          disabled={selection.saving}
          onClick={onClose}
          aria-label="Đóng thêm source"
        >
          <XIcon />
        </Button>
      </div>
      <div className="space-y-6 p-4 md:p-6">
        <SourceDraftNotice selection={selection} />
        {selection.draftsReady ? (
          <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
            <div className="min-w-0 space-y-6">
              <NewSourceForm
                selection={selection}
                allowedKinds={["image", "video"]}
              />
              <SourceSaveForm selection={selection} />
              {selection.saveError && (
                <p role="alert" className="text-sm text-destructive">
                  {selection.saveError}
                </p>
              )}
              {selection.notice && (
                <p role="status" className="text-sm text-success">
                  {selection.notice}
                </p>
              )}
            </div>
            <SourceDetails source={selection.source} />
          </div>
        ) : (
          <p role="status" className="text-sm text-muted-foreground">
            Đang khôi phục bản nháp…
          </p>
        )}
      </div>
    </section>
  );
}
