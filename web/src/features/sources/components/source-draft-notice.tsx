import { useState } from "react";
import { FileClockIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SourceSelection } from "../use-source-selection";

export function SourceDraftNotice({
  selection,
}: {
  selection: SourceSelection;
}) {
  const [discarding, setDiscarding] = useState(false);
  if (!selection.draftCount) return null;
  const active =
    selection.mode === "new" &&
    ((selection.source && !selection.source.saved) ||
      selection.location.trim());
  return (
    <div
      className="flex flex-col gap-3 rounded-lg bg-muted p-4 sm:flex-row sm:items-center sm:justify-between"
      role="status"
    >
      <div className="flex min-w-0 gap-3">
        <FileClockIcon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium">
            {active ? "Bản nháp chưa lưu" : `${selection.draftCount} bản nháp`}
          </p>
          {selection.storageStatus === "error" && (
            <p className="text-xs text-destructive">
              Không giữ được nháp qua reload. Hãy lưu source.
            </p>
          )}
          {discarding && (
            <p className="text-xs text-destructive">Bỏ bản nháp này?</p>
          )}
        </div>
      </div>
      {!active ? (
        <Button
          size="sm"
          variant="outline"
          disabled={selection.saving}
          onClick={selection.resumeDraft}
        >
          Mở lại nháp
        </Button>
      ) : (
        <div className="flex shrink-0 gap-2">
          {discarding ? (
            <>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => {
                  selection.discardDraft();
                  setDiscarding(false);
                }}
              >
                Bỏ bản nháp
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setDiscarding(false)}
              >
                Giữ lại
              </Button>
            </>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              disabled={selection.saving}
              onClick={() => setDiscarding(true)}
            >
              Bỏ nháp
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
