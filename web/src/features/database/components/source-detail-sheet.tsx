import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { SourceDetails } from "@/features/sources/components/source-details";
import { SavedSourceActions } from "@/features/sources/components/saved-source-actions";
import type { VisionSource } from "@/features/sources/types";
import type { SourceSelection } from "@/features/sources/use-source-selection";

export function SourceDetailSheet({
  source,
  selection,
  error,
  onClose,
}: {
  source: VisionSource | null;
  selection: Pick<SourceSelection, "saving" | "rename" | "remove">;
  error: string;
  onClose: () => void;
}) {
  return (
    <Sheet
      open={Boolean(source)}
      onOpenChange={(open) => {
        if (!open && !selection.saving) onClose();
      }}
    >
      <SheetContent
        className="w-full overflow-y-auto sm:max-w-lg"
        onEscapeKeyDown={(event) => {
          if (selection.saving) event.preventDefault();
        }}
        onPointerDownOutside={(event) => {
          if (selection.saving) event.preventDefault();
        }}
      >
        <SheetHeader className="border-b p-4 pr-14 md:p-6">
          <SheetTitle>Chi tiết source</SheetTitle>
          <SheetDescription className="sr-only">
            Xem trước, đổi tên hoặc xoá source đã lưu.
          </SheetDescription>
        </SheetHeader>
        {source && (
          <div className="space-y-6 px-4 pb-6 md:px-6 [&_aside]:border-0 [&_aside]:p-0">
            <SourceDetails source={source} />
            <div className="border-t pt-4">
              <SavedSourceActions
                key={source.id}
                source={source}
                selection={selection}
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
