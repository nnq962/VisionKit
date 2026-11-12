import { BookmarkPlusIcon, CheckIcon, LoaderCircleIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SourceSelection } from "../use-source-selection";

export function SourceSaveForm({ selection }: { selection: SourceSelection }) {
  if (["stream", "youtube", "webcam"].includes(selection.kind)) return null;
  const source = selection.source;
  if (source?.saved)
    return (
      <p
        role="status"
        className="flex items-center gap-2 border-t pt-4 text-sm text-success"
      >
        <CheckIcon className="size-4" />
        Đã lưu trong thư viện
      </p>
    );
  const canSave = Boolean(
    source &&
    ["image", "screen", "video"].includes(source.kind) &&
    ["ready", "pending"].includes(source.status),
  );
  return (
    <form
      className="space-y-2 border-t pt-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSave && !selection.saving && selection.saveName.trim())
          void selection.save();
      }}
    >
      <Label htmlFor="source-name">Tên nguồn</Label>
      <div className="flex flex-wrap gap-2">
        <Input
          id="source-name"
          className="h-9 min-w-32 flex-1"
          value={selection.saveName}
          onChange={(event) => selection.setSaveName(event.target.value)}
          placeholder="Tên trong thư viện"
          maxLength={120}
          disabled={!source || selection.saving}
        />
        <Button
          type="submit"
          size="lg"
          variant="outline"
          disabled={!canSave || !selection.saveName.trim() || selection.saving}
        >
          {selection.saving ? (
            <LoaderCircleIcon className="animate-spin motion-reduce:animate-none" />
          ) : (
            <BookmarkPlusIcon />
          )}
          Lưu nguồn
        </Button>
      </div>
      {selection.saveError && (
        <p role="alert" className="text-sm text-destructive">
          {selection.saveError}
        </p>
      )}
    </form>
  );
}
