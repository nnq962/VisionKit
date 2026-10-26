import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { ModelDetails } from "@/features/models/components/model-details";
import type { useModelCatalog } from "../use-model-catalog";

import { StorageDetails } from "./storage-details";

type Catalog = ReturnType<typeof useModelCatalog>;

export function ModelDetailSheet({ catalog }: { catalog: Catalog }) {
  const model = catalog.selected;
  const storage: [string, string][] = model
    ? [
        ["ID", model.id],
        ["Vị trí lưu", `models/${model.location}`],
        [
          "Dung lượng chính xác",
          `${model.sizeBytes.toLocaleString("vi-VN")} byte`,
        ],
        ["Ngày lưu", new Date(model.savedAt).toLocaleString("vi-VN")],
        ["SHA-256 đầy đủ", model.sha256],
      ]
    : [];
  return (
    <Sheet
      open={Boolean(model)}
      onOpenChange={(open) => {
        if (!open) catalog.close();
      }}
    >
      <SheetContent className="w-full overflow-y-auto data-[side=right]:w-full sm:max-w-lg">
        <SheetHeader className="border-b p-4 pr-14 md:p-6">
          <SheetTitle>Chi tiết model</SheetTitle>
          <SheetDescription className="sr-only">
            Metadata và thông tin lưu trữ của model đã lưu.
          </SheetDescription>
        </SheetHeader>
        {model && (
          <div className="space-y-6 px-4 pb-6 md:px-6 [&_aside]:border-0 [&_aside]:p-0">
            <ModelDetails model={model} selection={catalog} />
            {catalog.actionError && (
              <p role="alert" className="text-sm text-destructive">
                {catalog.actionError}
              </p>
            )}
            <StorageDetails rows={storage} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
