import { SourceSaveForm } from "@/features/sources/components/source-save-form";
import { BookmarkIcon, PlusIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SourceDraftNotice } from "@/features/sources/components/source-draft-notice";
import { NewSourceForm } from "@/features/sources/components/new-source-form";
import { SavedSourceList } from "@/features/sources/components/saved-source-list";
import { SourceDetails } from "@/features/sources/components/source-details";
import type { SourceSelection } from "@/features/sources/use-source-selection";

export function SourceStep({ selection }: { selection: SourceSelection }) {
  const mode = selection.mode;
  if (!selection.draftsReady)
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Đang khôi phục bản nháp…
      </p>
    );
  return (
    <div className="space-y-6">
      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label="Cách chọn source"
      >
        <Button
          variant={mode === "new" ? "secondary" : "ghost"}
          aria-pressed={mode === "new"}
          disabled={selection.saving}
          onClick={() => selection.setMode("new")}
        >
          <PlusIcon />
          Source mới
          {selection.draftCount > 0 && (
            <span className="rounded bg-accent px-1.5 py-0.5 text-xs text-accent-foreground">
              {selection.draftCount} nháp
            </span>
          )}
        </Button>
        <Button
          variant={mode === "saved" ? "secondary" : "ghost"}
          aria-pressed={mode === "saved"}
          disabled={selection.saving}
          onClick={() => selection.setMode("saved")}
        >
          <BookmarkIcon />
          Đã lưu ({selection.libraryTotal})
        </Button>
      </div>
      <SourceDraftNotice
        key={`${mode}-${selection.kind}`}
        selection={selection}
      />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          {mode === "new" ? (
            <NewSourceForm selection={selection} />
          ) : (
            <SavedSourceList selection={selection} />
          )}
          {mode === "new" && <SourceSaveForm selection={selection} />}
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
        <div
          aria-live="polite"
          aria-busy={selection.source?.status === "loading"}
        >
          <SourceDetails
            source={selection.source}
            onOpenCamera={
              mode === "saved" ? () => void selection.openCamera() : undefined
            }
          />
        </div>
      </div>
    </div>
  );
}
