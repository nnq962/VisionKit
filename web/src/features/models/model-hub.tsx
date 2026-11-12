"use client";

import { useState } from "react";
import {
  BookmarkIcon,
  CompassIcon,
  SearchIcon,
  DownloadIcon,
  RefreshCwIcon,
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
import {
  taskLabels,
  modelTaskLabel,
  modelGroup,
  modelGroupLabels,
  compareModelFamilies,
  type ModelGroup,
  type ModelTask,
} from "./catalog";
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
  const modelFamilies = [...downloads.families].sort((a, b) =>
    compareModelFamilies(a.id, b.id),
  );
  const groupFamilies = modelFamilies.filter(
    (item) => family === "all" || modelGroup(item.id) === family,
  );
  const availableTasks = new Set(
    tab === "saved"
      ? downloads.saved
          .filter(
            (item) => family === "all" || modelGroup(item.familyId) === family,
          )
          .flatMap((item) => (item.task ? [item.task] : []))
      : groupFamilies.flatMap((item) => item.tasks),
  );
  const query = search.trim().toLowerCase();
  const families = modelFamilies.filter(
    (item) =>
      (family === "all" || modelGroup(item.id) === family) &&
      (task === "all" || item.tasks.includes(task)) &&
      `${item.name} ${item.prefix} ${item.tasks.map((t) => taskLabels[t]).join(" ")}`
        .toLowerCase()
        .includes(query),
  );
  const saved = downloads.saved
    .filter(
      (item) =>
        (family === "all" || modelGroup(item.familyId) === family) &&
        (task === "all" || item.task === task) &&
        `${item.name ?? ""} ${item.filename} ${item.familyName} ${modelTaskLabel(item.task)}`
          .toLowerCase()
          .includes(query),
    )
    .sort((a, b) => compareModelFamilies(a.familyId, b.familyId));
  const filtered = Boolean(query) || task !== "all" || family !== "all";
  const running = downloads.history.filter((job) =>
    ["queued", "downloading"].includes(job.status),
  ).length;

  function clearFilters() {
    setSearch("");
    setTask("all");
    setFamily("all");
  }
  function switchTab(next: typeof tab) {
    setTab(next);
  }
  const count =
    tab === "catalog"
      ? `${families.length} dòng model`
      : tab === "saved"
        ? `${saved.length} model`
        : `${Object.keys(downloads.jobs).length} lượt tải`;
  return (
    <WorkspacePage title="Model Hub" hideHeading>
      <WorkspaceSection
        title="Model Hub"
        titleId="models-heading"
        showHeader={false}
        variant="plain"
        toolbarLabel="Công cụ model"
        bodyLabel="Danh sách model"
        compactFooter
        toolbar={
          <div className="w-full space-y-4">
            <div className="flex items-center justify-between gap-2">
              <div
                role="group"
                aria-label="Danh mục model"
                className="inline-flex min-w-0 flex-wrap gap-1 rounded-lg bg-muted/60 p-1"
              >
                {(
                  [
                    {
                      id: "catalog",
                      label: "Khám phá",
                      Icon: CompassIcon,
                      count: null,
                    },
                    {
                      id: "saved",
                      label: "Đã lưu",
                      Icon: BookmarkIcon,
                      count: downloads.ready ? downloads.saved.length : null,
                    },
                    {
                      id: "downloads",
                      label: "Lượt tải",
                      Icon: DownloadIcon,
                      count: running || null,
                    },
                  ] as const
                ).map(({ id, label, Icon, count }) => (
                  <Button
                    key={id}
                    size="default"
                    variant={tab === id ? "outline" : "ghost"}
                    className="max-sm:px-2 max-sm:[&_svg]:hidden"
                    aria-pressed={tab === id}
                    onClick={() => switchTab(id)}
                  >
                    <Icon />
                    {label}
                    {count !== null && (
                      <span className="text-xs tabular-nums text-muted-foreground">
                        {count}
                      </span>
                    )}
                  </Button>
                ))}
              </div>
              <Button
                size="icon-lg"
                variant="ghost"
                aria-label="Làm mới model"
                title="Làm mới"
                onClick={downloads.refresh}
              >
                <RefreshCwIcon />
              </Button>
            </div>
            {tab !== "downloads" && (
              <div className="flex flex-col gap-2 sm:flex-row">
                <div className="relative min-w-0 flex-1">
                  <SearchIcon className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 size-4 text-muted-foreground" />
                  <Input
                    aria-label="Tìm model"
                    placeholder={
                      tab === "saved" ? "Tìm model đã lưu…" : "Tìm dòng model…"
                    }
                    className="h-9 pl-9"
                    value={search}
                    onChange={(event) => {
                      setSearch(event.target.value);
                    }}
                  />
                </div>
                <div className="grid grid-cols-2 gap-2 sm:flex">
                  <Select
                    value={family}
                    onValueChange={(value) => {
                      const next = value as ModelGroup | "all";
                      setFamily(next);
                      if (
                        task !== "all" &&
                        !modelFamilies.some(
                          (item) =>
                            (next === "all" || modelGroup(item.id) === next) &&
                            item.tasks.includes(task),
                        )
                      )
                        setTask("all");
                    }}
                  >
                    <SelectTrigger
                      aria-label="Lọc nhóm model"
                      className="data-[size=default]:h-9 w-full sm:w-36"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {Object.entries(modelGroupLabels).map(
                          ([value, label]) => (
                            <SelectItem value={value} key={value}>
                              {label}
                            </SelectItem>
                          ),
                        )}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  <Select
                    value={task}
                    onValueChange={(value) => {
                      setTask(value as ModelTask | "all");
                    }}
                  >
                    <SelectTrigger
                      aria-label="Lọc tác vụ"
                      className="data-[size=default]:h-9 w-full sm:w-40"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        <SelectItem value="all">Tất cả tác vụ</SelectItem>
                        {Object.entries(taskLabels)
                          .filter(([value]) =>
                            availableTasks.has(value as ModelTask),
                          )
                          .map(([value, label]) => (
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
          </div>
        }
        footer={
          <div className="flex w-full flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span className="tabular-nums">
              {count}
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
        <div className="space-y-3">
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
              onClearFilters={clearFilters}
              busy={downloads.busy}
            />
          )}
        </div>
      </WorkspaceSection>
    </WorkspacePage>
  );
}
