"use client";

import { useState } from "react";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
} from "lucide-react";
import { WorkspaceSection } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getSource } from "@/features/sources/api";
import { useSourceSelection } from "@/features/sources/source-provider";
import type { SourceKind, VisionSource } from "@/features/sources/types";
import { useSourceCatalog } from "./use-source-catalog";
import { SourceTable } from "./components/source-table";
import { SourceUploadPanel } from "./components/source-upload-panel";
import { SourceDetailSheet } from "./components/source-detail-sheet";

export function SourceDatabase() {
  const selection = useSourceSelection();
  const [revision, setRevision] = useState(0);
  const catalog = useSourceCatalog(`${revision}:${selection.libraryTotal}`);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [detail, setDetail] = useState<VisionSource | null>(null);
  const [actionError, setActionError] = useState("");

  function openUpload() {
    selection.setMode("new");
    if (!["image", "video", "stream"].includes(selection.kind))
      selection.setKind("image");
    setUploadOpen(true);
    requestAnimationFrame(() =>
      document.getElementById("upload-heading")?.focus(),
    );
  }

  return (
    <>
      {uploadOpen && (
        <SourceUploadPanel
          selection={selection}
          onClose={() => setUploadOpen(false)}
        />
      )}
      <WorkspaceSection
        title="Thư viện source"
        titleId="source-library-heading"
        footer={
          <>
            <p
              role="status"
              className="text-xs text-muted-foreground tabular-nums"
            >
              {catalog.total
                ? `${catalog.page * catalog.limit + 1}–${Math.min((catalog.page + 1) * catalog.limit, catalog.total)} / ${catalog.total} source`
                : "0 source"}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Trang trước"
                disabled={catalog.page === 0 || catalog.loading}
                onClick={() => catalog.setPage(catalog.page - 1)}
              >
                <ChevronLeftIcon />
              </Button>
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Trang sau"
                disabled={
                  (catalog.page + 1) * catalog.limit >= catalog.total ||
                  catalog.loading
                }
                onClick={() => catalog.setPage(catalog.page + 1)}
              >
                <ChevronRightIcon />
              </Button>
            </div>
          </>
        }
      >
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative min-w-0 flex-1">
              <SearchIcon className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground" />
              <Input
                aria-label="Tìm source"
                placeholder="Tìm theo tên…"
                className="pl-9"
                value={catalog.search}
                maxLength={120}
                onChange={(event) => catalog.setSearch(event.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <Select
                value={catalog.kind}
                onValueChange={(value) =>
                  catalog.setKind(value as SourceKind | "all")
                }
              >
                <SelectTrigger className="w-36" aria-label="Lọc loại source">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="all">Tất cả loại</SelectItem>
                    <SelectItem value="image">Ảnh</SelectItem>
                    <SelectItem value="video">Video</SelectItem>
                    <SelectItem value="stream">Camera RTSP</SelectItem>
                    <SelectItem value="screen">Ảnh màn hình</SelectItem>
                  </SelectGroup>
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="icon"
                aria-label="Làm mới thư viện"
                disabled={catalog.loading}
                onClick={() => {
                  catalog.refresh();
                  void selection.refreshLibrary();
                }}
              >
                <RefreshCwIcon
                  className={
                    catalog.loading
                      ? "animate-spin motion-reduce:animate-none"
                      : ""
                  }
                />
              </Button>
              <Button
                onClick={openUpload}
                disabled={selection.saving || !selection.draftsReady}
              >
                <PlusIcon />
                Thêm source
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
          ) : (
            <SourceTable
              items={catalog.items}
              loading={catalog.loading}
              filtered={
                Boolean(catalog.search.trim()) || catalog.kind !== "all"
              }
              onOpen={(source) => {
                setDetail(source);
                setActionError("");
              }}
              onAdd={openUpload}
            />
          )}
        </div>
      </WorkspaceSection>
      <SourceDetailSheet
        source={detail}
        error={actionError}
        onClose={() => setDetail(null)}
        selection={{
          saving: selection.saving,
          rename: async (id, name) => {
            const ok = await selection.rename(id, name);
            if (ok) {
              setDetail((current) => (current ? { ...current, name } : null));
              setActionError("");
              setRevision((value) => value + 1);
            } else setActionError("Không đổi được tên. Thử lại.");
            return ok;
          },
          configureRtsp: async (name, url, id) => {
            const ok = await selection.configureRtsp(name, url, id);
            if (ok) {
              if (id) {
                const refreshed = await getSource(id).catch(() => null);
                if (refreshed) setDetail(refreshed);
              }
              setActionError("");
              setRevision((value) => value + 1);
            } else setActionError("Không lưu được cấu hình camera. Kiểm tra kết nối rồi thử lại.");
            return ok;
          },
          remove: async (id) => {
            const ok = await selection.remove(id);
            if (ok) {
              setDetail(null);
              setRevision((value) => value + 1);
            } else setActionError("Không xoá được source. Thử lại.");
            return ok;
          },
        }}
      />
    </>
  );
}
