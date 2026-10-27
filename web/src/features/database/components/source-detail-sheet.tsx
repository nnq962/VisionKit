import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { StorageDetails } from "./storage-details";
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
  selection: Pick<SourceSelection, "saving" | "rename" | "remove" | "configureRtsp">;
  error: string;
  onClose: () => void;
}) {
  const storage: [string, string][] = source?.kind === "stream"
    ? [["ID", source.id], ["Địa chỉ camera", source.location], ["Ngày thêm", source.createdAt ? new Date(source.createdAt).toLocaleString("vi-VN") : "—"]]
    : source
    ? [
        ["ID", source.id],
        ["Tệp gốc", source.originalFilename ?? "Chưa ghi nhận"],
        [
          "Vị trí lưu",
          ["image", "screen", "video"].includes(source.kind)
            ? `sources/${source.location}`
            : source.location,
        ],
        [
          "Dung lượng chính xác",
          source.size !== undefined
            ? `${source.size.toLocaleString("vi-VN")} byte`
            : "Chưa ghi nhận",
        ],
        ["MIME", source.mimeType ?? "Chưa ghi nhận"],
        [
          "Ngày lưu",
          source.createdAt
            ? new Date(source.createdAt).toLocaleString("vi-VN")
            : "Chưa ghi nhận",
        ],
        [
          "Cập nhật lần cuối",
          source.updatedAt
            ? new Date(source.updatedAt).toLocaleString("vi-VN")
            : "Chưa ghi nhận",
        ],
        ...(source.previewLocation
          ? [
              ["Tệp preview", `sources/${source.previewLocation}`] as [
                string,
                string,
              ],
            ]
          : []),
        ...(source.previewSize !== undefined
          ? [
              [
                "Dung lượng preview",
                `${source.previewSize.toLocaleString("vi-VN")} byte`,
              ] as [string, string],
            ]
          : []),
        ["SHA-256 đầy đủ", source.sha256 ?? "Chưa ghi nhận"],
      ]
    : [];
  return (
    <Sheet
      open={Boolean(source)}
      onOpenChange={(open) => {
        if (!open && !selection.saving) onClose();
      }}
    >
      <SheetContent
        className="w-full overflow-y-auto data-[side=right]:w-full sm:max-w-lg"
        onEscapeKeyDown={(event) => {
          if (selection.saving) event.preventDefault();
        }}
        onPointerDownOutside={(event) => {
          if (selection.saving) event.preventDefault();
        }}
      >
        <SheetHeader className="border-b p-4 pr-14 md:p-6">
          <SheetTitle>{source?.kind === "stream" ? source.name : "Chi tiết source"}</SheetTitle>
          <SheetDescription className="sr-only">
            Xem trước, sửa cấu hình, đổi tên hoặc xoá source đã lưu.
          </SheetDescription>
        </SheetHeader>
        {source && (
          <div className="space-y-6 px-4 pb-6 md:px-6 [&_aside]:border-0 [&_aside]:p-0">
            <div className="space-y-6">
              <SourceDetails source={source} />
              <StorageDetails rows={storage} />
            </div>
            <div className="border-t">
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
