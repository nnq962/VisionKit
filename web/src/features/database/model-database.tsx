"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowUpRightIcon,
  BoxIcon,
  ChevronRightIcon,
  RefreshCwIcon,
  SearchIcon,
} from "lucide-react";
import { WorkspaceSection } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { formatBytes } from "@/features/sources/media-metadata";
import { modelTaskLabel } from "@/features/models/catalog";
import { ModelDetailSheet } from "./components/model-detail-sheet";
import { useModelCatalog } from "./use-model-catalog";

export function ModelDatabase() {
  const catalog = useModelCatalog();
  const [search, setSearch] = useState("");
  const [format, setFormat] = useState("all");
  const [limit, setLimit] = useState(20);
  const query = search.trim().toLocaleLowerCase("vi");
  const items = catalog.items.filter(
    (model) =>
      (format === "all" || model.format === format) &&
      `${model.name ?? ""} ${model.filename} ${model.familyName} ${model.inspection.metadata?.model_series ?? ""} ${modelTaskLabel(model.task)}`
        .toLocaleLowerCase("vi")
        .includes(query),
  );
  const totalBytes = items.reduce((sum, model) => sum + model.sizeBytes, 0);
  return (
    <>
      <WorkspaceSection
        title="Thư viện model"
        titleId="model-library-heading"
        footer={
          <>
            <p
              role="status"
              className="text-xs text-muted-foreground tabular-nums"
            >
              {items.length} model · {formatBytes(totalBytes)} đã lưu
            </p>
            {items.length > limit && (
              <Button
                variant="outline"
                onClick={() => setLimit((value) => value + 20)}
              >
                Xem thêm
              </Button>
            )}
          </>
        }
      >
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative min-w-0 flex-1">
              <SearchIcon className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground" />
              <Input
                aria-label="Tìm model"
                placeholder="Tìm theo tên, dòng model…"
                className="pl-9"
                value={search}
                maxLength={120}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setLimit(20);
                }}
              />
            </div>
            <div className="flex gap-2">
              <Select
                value={format}
                onValueChange={(value) => {
                  setFormat(value);
                  setLimit(20);
                }}
              >
                <SelectTrigger
                  className="min-w-0 flex-1 sm:w-36 sm:flex-none"
                  aria-label="Lọc định dạng model"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="all">Tất cả định dạng</SelectItem>
                    <SelectItem value="pt">PT</SelectItem>
                    <SelectItem value="onnx">ONNX</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="icon"
                aria-label="Làm mới model"
                disabled={catalog.loading}
                onClick={catalog.refresh}
              >
                <RefreshCwIcon
                  className={
                    catalog.loading
                      ? "animate-spin motion-reduce:animate-none"
                      : ""
                  }
                />
              </Button>
              <Button variant="outline" asChild>
                <Link href="/models">
                  Model Hub
                  <ArrowUpRightIcon />
                </Link>
              </Button>
            </div>
          </div>
          {catalog.error ? (
            <div role="alert" className="space-y-3 py-8">
              <p className="text-sm text-destructive">{catalog.error}</p>
              <Button variant="outline" onClick={catalog.refresh}>
                Thử lại
              </Button>
            </div>
          ) : catalog.loading && !catalog.items.length ? (
            <div
              role="status"
              aria-label="Đang tải model"
              className="space-y-4 py-4"
            >
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : !items.length ? (
            <div className="flex min-h-64 flex-col items-center justify-center gap-3 text-center">
              <BoxIcon
                className="size-8 text-muted-foreground"
                strokeWidth={1.5}
              />
              <p className="text-sm font-medium">
                {query || format !== "all"
                  ? "Không tìm thấy model"
                  : "Chưa có model đã lưu"}
              </p>
              {!query && format === "all" && (
                <Button variant="outline" asChild>
                  <Link href="/models">Mở Model Hub</Link>
                </Button>
              )}
            </div>
          ) : (
            <div>
              <div
                aria-hidden="true"
                className="hidden grid-cols-[minmax(0,1fr)_5rem_7rem_6rem_1rem] gap-4 border-b px-3 pb-3 text-xs text-muted-foreground md:grid"
              >
                <span>Model</span>
                <span>Định dạng</span>
                <span>Dung lượng</span>
                <span>Ngày lưu</span>
                <span />
              </div>
              <ul className="divide-y" aria-label="Danh sách model">
                {items.slice(0, limit).map((model) => (
                  <li key={model.id}>
                    <button
                      onClick={() => catalog.open(model.id)}
                      className="flex w-full items-center gap-3 rounded-lg px-2 py-4 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring md:grid md:grid-cols-[minmax(0,1fr)_5rem_7rem_6rem_1rem] md:gap-4 md:px-3"
                    >
                      <span className="flex min-w-0 flex-1 items-center gap-3">
                        <BoxIcon
                          className="size-6 shrink-0 text-muted-foreground"
                          strokeWidth={1.5}
                        />
                        <span className="min-w-0 space-y-1">
                          <span className="block truncate text-sm font-medium">
                            {model.name ?? model.filename}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {model.inspection.metadata?.model_series ??
                              model.familyName}{" "}
                            · {modelTaskLabel(model.task)}
                            <span className="md:hidden">
                              {" "}
                              · {(model.format ?? "pt").toUpperCase()} ·{" "}
                              {formatBytes(model.sizeBytes)}
                            </span>
                          </span>
                        </span>
                      </span>
                      <span className="hidden text-sm text-muted-foreground md:block">
                        {(model.format ?? "pt").toUpperCase()}
                      </span>
                      <span className="hidden text-sm text-muted-foreground tabular-nums md:block">
                        {formatBytes(model.sizeBytes)}
                      </span>
                      <span className="hidden text-xs text-muted-foreground tabular-nums md:block">
                        {new Date(model.savedAt).toLocaleDateString("vi-VN")}
                      </span>
                      <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground" />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </WorkspaceSection>
      <ModelDetailSheet catalog={catalog} />
    </>
  );
}
