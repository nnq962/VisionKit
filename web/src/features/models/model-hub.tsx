"use client";

import { useState } from "react";
import {
  BookmarkIcon,
  CompassIcon,
  SearchIcon,
  DownloadIcon,
} from "lucide-react";
import { WorkspacePage, WorkspaceSection } from "@/components/workspace-page";
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
import { taskLabels, modelTaskLabel, modelGroup, modelGroupLabels, compareModelFamilies, type ModelGroup, type ModelTask } from "./catalog";
import { useModelDownloads } from "./use-model-downloads";
import { ModelCatalogRow } from "./components/model-catalog-row";
import { ModelDownloadList } from "./components/model-download-list";
import { SavedModelList } from "./components/saved-model-list";

export function ModelHub() {
  const [tab, setTab] = useState<"catalog" | "saved" | "downloads">("catalog");
  const [search, setSearch] = useState("");
  const [task, setTask] = useState<ModelTask | "all">("all");
  const [family, setFamily] = useState<ModelGroup | "all">("all");
  const downloads = useModelDownloads();
  const modelFamilies = [...downloads.families].sort((a, b) => compareModelFamilies(a.id, b.id));
  const groupFamilies = modelFamilies.filter((item) => family === "all" || modelGroup(item.id) === family);
  const availableTasks = new Set(groupFamilies.flatMap((item) => item.tasks));
  const query = search.trim().toLowerCase();
  const families = modelFamilies.filter(
    (item) =>
      (family === "all" || modelGroup(item.id) === family) &&
      (task === "all" || item.tasks.includes(task)) &&
      `${item.name} ${item.prefix} ${item.tasks.map((t) => taskLabels[t]).join(" ")}`
        .toLowerCase()
        .includes(query),
  );
  const saved = downloads.saved.filter(
    (item) =>
      (family === "all" || modelGroup(item.familyId) === family) &&
      (task === "all" || item.task === task) &&
      `${item.name ?? ""} ${item.filename} ${item.familyName} ${modelTaskLabel(item.task)}`
        .toLowerCase()
        .includes(query),
  ).sort((a, b) => compareModelFamilies(a.familyId, b.familyId));
  const filtered = Boolean(query) || task !== "all" || family !== "all";
  const running = downloads.history.filter((job) =>
    ["queued", "downloading"].includes(job.status),
  ).length;
  return (
    <WorkspacePage
      title="Model Hub"
      description="Khám phá model YOLO và thêm vào thư viện."
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div
          role="group"
          aria-label="Danh mục model"
          className="flex flex-wrap gap-2"
        >
          <Button
            variant={tab === "catalog" ? "secondary" : "ghost"}
            aria-pressed={tab === "catalog"}
            onClick={() => setTab("catalog")}
          >
            <CompassIcon />
            Khám phá
          </Button>
          <Button
            variant={tab === "saved" ? "secondary" : "ghost"}
            aria-pressed={tab === "saved"}
            onClick={() => setTab("saved")}
          >
            <BookmarkIcon />
            Đã lưu
            {downloads.ready && (
              <span className="ml-1 text-xs tabular-nums">
                {downloads.saved.length}
              </span>
            )}
          </Button>
          <Button
            variant={tab === "downloads" ? "secondary" : "ghost"}
            aria-pressed={tab === "downloads"}
            onClick={() => setTab("downloads")}
          >
            <DownloadIcon />
            Lượt tải
            {running > 0 && (
              <span className="ml-1 text-xs tabular-nums">{running}</span>
            )}
          </Button>
        </div>
      </div>
      <WorkspaceSection
        title={
          tab === "catalog"
            ? "Danh mục Ultralytics"
            : tab === "downloads"
              ? "Lượt tải model"
              : "Thư viện model"
        }
        titleId="models-heading"
        footer={
          <div className="flex w-full flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
            <span>
              {tab === "catalog"
                ? `${families.length} dòng model`
                : tab === "downloads"
                  ? `${Object.values(downloads.jobs).length} lượt tải`
                  : `${saved.length} model`}
              {running > 0 ? ` · ${running} đang tải` : ""}
            </span>
            <a
              href="https://docs.ultralytics.com/models/"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-4 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
            >
              Tài liệu Ultralytics
            </a>
          </div>
        }
      >
        <div className="space-y-6">
          {tab !== "downloads" && (
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative min-w-0 flex-1">
                <SearchIcon className="pointer-events-none absolute top-2.5 left-3 size-4 text-muted-foreground" />
                <Input
                  aria-label="Tìm model"
                  placeholder="Tìm dòng model…"
                  className="pl-9"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-2 sm:flex">
                <Select value={family} onValueChange={(value) => {
                  const next = value as ModelGroup | "all";
                  setFamily(next);
                  if (task !== "all" && !modelFamilies.some((item) =>
                    (next === "all" || modelGroup(item.id) === next) && item.tasks.includes(task),
                  )) setTask("all");
                }}>
                  <SelectTrigger
                    aria-label="Lọc nhóm model"
                    className="w-full sm:w-36"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {Object.entries(modelGroupLabels).map(([value, label]) => (
                        <SelectItem value={value} key={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
                <Select
                  value={task}
                  onValueChange={(value) => setTask(value as ModelTask | "all")}
                >
                  <SelectTrigger
                    aria-label="Lọc tác vụ"
                    className="w-full sm:w-40"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="all">Tất cả tác vụ</SelectItem>
                      {Object.entries(taskLabels).filter(([value]) => availableTasks.has(value as ModelTask)).map(([value, label]) => (
                        <SelectItem value={value} key={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          {downloads.error && (
            <div role="alert" className="flex flex-wrap items-center gap-3">
              <p className="text-sm text-destructive">{downloads.error}</p>
              <Button variant="outline" size="sm" onClick={downloads.refresh}>
                Làm mới
              </Button>
            </div>
          )}
          <p role="status" className="sr-only">
            {downloads.notice}
          </p>
          {tab === "downloads" &&
          !downloads.ready &&
          !downloads.history.length ? (
            downloads.error ? null : (
              <p
                role="status"
                className="py-10 text-center text-sm text-muted-foreground"
              >
                Đang tải lượt tải…
              </p>
            )
          ) : tab === "downloads" ? (
            <ModelDownloadList
              jobs={Object.values(downloads.jobs)}
              busy={downloads.busy}
              onCancel={downloads.cancel}
              onRetry={downloads.download}
            />
          ) : tab === "catalog" ? (
            families.length ? (
              <ul className="divide-y" aria-label="Danh mục model Ultralytics">
                {families.map((item) => (
                  <ModelCatalogRow
                    key={item.id}
                    family={item}
                    taskFilter={task}
                    saved={downloads.saved}
                    jobs={downloads.jobs}
                    ready={downloads.ready}
                    busy={downloads.busy}
                    onDownload={downloads.download}
                    onCancel={downloads.cancel}
                  />
                ))}
              </ul>
            ) : !modelFamilies.length &&
              downloads.error ? null : !downloads.ready && !downloads.error ? (
              <p
                role="status"
                className="py-10 text-center text-sm text-muted-foreground"
              >
                Đang tải danh mục…
              </p>
            ) : (
              <div className="flex min-h-56 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
                <p>Không tìm thấy model</p>
                <Button
                  variant="outline"
                  onClick={() => {
                    setSearch("");
                    setTask("all");
                    setFamily("all");
                  }}
                >
                  Xoá bộ lọc
                </Button>
              </div>
            )
          ) : !downloads.ready && !saved.length ? (
            downloads.error ? null : (
              <p
                role="status"
                className="py-10 text-center text-sm text-muted-foreground"
              >
                Đang tải thư viện…
              </p>
            )
          ) : (
            <SavedModelList
              items={saved}
              onRemove={downloads.remove}
              onBrowse={() => setTab("catalog")}
              filtered={filtered}
              busy={downloads.busy}
            />
          )}
        </div>
      </WorkspaceSection>
    </WorkspacePage>
  );
}
