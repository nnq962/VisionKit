import { useEffect, useRef } from "react";
import { BookmarkIcon, UploadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ModelLibraryPicker } from "@/features/models/components/model-library-picker";
import { ModelUploadForm } from "@/features/models/components/model-upload-form";
import { ModelDetails } from "@/features/models/components/model-details";
import type { ModelSelection } from "@/features/models/use-model-selection";

export function ModelStep({ selection }: { selection: ModelSelection }) {
  const refresh = useRef(selection.refresh);
  useEffect(() => {
    refresh.current();
  }, []);
  if (!selection.draftsReady)
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Đang khôi phục model…
      </p>
    );
  return (
    <div className="space-y-6">
      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label="Cách chọn model"
      >
        <Button
          variant={selection.mode === "saved" ? "secondary" : "ghost"}
          aria-pressed={selection.mode === "saved"}
          disabled={
            selection.uploading || selection.saving || selection.validating
          }
          onClick={() => selection.update({ mode: "saved" })}
        >
          <BookmarkIcon />
          Đã có ({selection.library.length})
        </Button>
        <Button
          variant={selection.mode === "upload" ? "secondary" : "ghost"}
          aria-pressed={selection.mode === "upload"}
          disabled={
            selection.uploading || selection.saving || selection.validating
          }
          onClick={() => selection.update({ mode: "upload" })}
        >
          <UploadIcon />
          Tải lên
          {selection.file && (
            <span className="rounded bg-accent px-1.5 py-0.5 text-xs text-accent-foreground">
              Nháp
            </span>
          )}
        </Button>
      </div>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-6">
          {selection.mode === "saved" ? (
            <ModelLibraryPicker selection={selection} />
          ) : (
            <ModelUploadForm selection={selection} />
          )}
          {selection.error && (
            <p role="alert" className="text-sm text-destructive">
              {selection.error}
            </p>
          )}
          {selection.draftError && (
            <p role="status" className="text-xs text-muted-foreground">
              {selection.draftError}
            </p>
          )}
        </div>
        <ModelDetails
          model={selection.selected}
          selection={selection}
          draft={selection.mode === "upload" ? selection : undefined}
        />
      </div>
    </div>
  );
}
