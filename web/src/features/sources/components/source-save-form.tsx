import { BookmarkIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SourceSelection } from "../use-source-selection";

export function SourceSaveForm({ selection }: { selection: SourceSelection }) {
  const canSave =
    selection.source &&
    ["image", "screen", "video"].includes(selection.source.kind) &&
    !selection.saving &&
    ["ready", "pending"].includes(selection.source.status);
  return (
    <div className="space-y-4 border-t pt-6">
      <div className="flex items-start gap-3">
        <input
          id="save-source"
          type="checkbox"
          className="mt-0.5 size-4 accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          checked={selection.saveEnabled}
          onChange={(event) => selection.setSaveEnabled(event.target.checked)}
          disabled={!canSave}
        />
        <div className="space-y-1">
          <Label htmlFor="save-source">Lưu vào thư viện</Label>
          {!["image", "screen", "video"].includes(selection.kind) && (
            <p className="text-xs text-muted-foreground">
              Chưa hỗ trợ lưu loại này.
            </p>
          )}
        </div>
      </div>
      {selection.saveEnabled && (
        <div className="space-y-2">
          <Label htmlFor="source-name">Tên dễ nhớ</Label>
          <Input
            id="source-name"
            value={selection.saveName}
            onChange={(event) => selection.setSaveName(event.target.value)}
            placeholder="Ví dụ: Camera cổng chính"
            maxLength={120}
          />
          <Button
            variant="outline"
            disabled={!selection.saveName.trim() || !canSave}
            onClick={() => void selection.save()}
          >
            <BookmarkIcon />
            {selection.saving ? "Đang lưu…" : "Lưu source"}
          </Button>
        </div>
      )}
    </div>
  );
}
