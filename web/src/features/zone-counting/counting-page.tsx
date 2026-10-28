"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckIcon,
  RefreshCwIcon,
  UploadIcon,
  BookmarkIcon,
  PlusIcon,
  SearchIcon,
  CopyIcon,
  Trash2Icon,
  SaveIcon,
} from "lucide-react";
import { toast } from "sonner";
import { VideoSourceInput } from "@/features/sources/components/video-source-input";
import { WorkspacePage, WorkspaceSection } from "@/components/workspace-page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  listSources,
  saveSource,
  configureRtspSource,
} from "@/features/sources/api";
import type { VisionSource } from "@/features/sources/types";
import { RtspCameraForm } from "@/features/sources/components/rtsp-camera-form";
import { getLibrary, type StoredModel } from "@/features/models/api";
import { SavedSourceItems } from "@/features/sources/components/saved-source-items";
import { SourceDetails } from "@/features/sources/components/source-details";
import { ModelDetails } from "@/features/models/components/model-details";
import { ModelLibraryPicker } from "@/features/models/components/model-library-picker";
import {
  listCountingProfiles,
  duplicateCountingProfile,
  deleteCountingProfile,
  restoreCountingProfile,
} from "./api";
import { profileSelectionKey, type CountingProfile } from "./types";
import { useUnsavedChanges } from "./use-unsaved-changes";
import { ZoneWorkspace, type CountingEditorHandle } from "./zone-workspace";

const steps = [
  "Chọn nguồn",
  "Chọn model",
  "Vùng và thông số",
  "Chạy và kết quả",
];

const selectionKey = "visionkit:medical-counting-selection:v1";

export function CountingPage({
  configureOnly = false,
}: {
  configureOnly?: boolean;
}) {
  const editor = useRef<CountingEditorHandle>(null);
  const visibleSteps = configureOnly ? steps.slice(0, 3) : steps;
  const [step, setStep] = useState(0);
  const restoreRun = useCallback(
    () => setStep(configureOnly ? 2 : 3),
    [configureOnly, setStep],
  );
  const [sources, setSources] = useState<VisionSource[]>([]);
  const [models, setModels] = useState<StoredModel[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [modelId, setModelId] = useState("");
  const [locked, setLocked] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sourceMode, setSourceMode] = useState<"new" | "saved">("saved");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [newSourceKind, setNewSourceKind] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("");
  const [revision, setRevision] = useState(0);
  const [profiles, setProfiles] = useState<CountingProfile[]>([]);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [profileName, setProfileName] = useState("Cấu hình 1");
  const [initialProfile, setInitialProfile] = useState<CountingProfile | null>(
    null,
  );
  const [editorVersion, setEditorVersion] = useState(0);
  const [workspaceDirty, setWorkspaceDirty] = useState(false);
  const [newTouched, setNewTouched] = useState(false);
  const [lastDeleted, setLastDeleted] = useState<CountingProfile | null>(null);
  const [managementError, setManagementError] = useState("");
  const selectedSaved = profiles.find((item) => item.id === profileId);
  const selectionDirty = selectedSaved
    ? profileName !== selectedSaved.name ||
      sourceId !== selectedSaved.source_id ||
      modelId !== selectedSaved.monitor.model_id
    : newTouched;
  async function duplicateProfile() {
    if (!profileId || busy) return;
    setBusy(true);
    setManagementError("");
    try {
      const copy = await duplicateCountingProfile(profileId);
      setProfiles((items) => [...items, copy]);
      // Mở đúng bản vừa tạo mà không chờ danh sách state của render tiếp theo.
      selectProfile(copy);
    } catch (reason) {
      setManagementError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function removeProfile() {
    if (!selectedSaved || busy) return;
    setBusy(true);
    setManagementError("");
    try {
      await deleteCountingProfile(selectedSaved.id);
      setLastDeleted(selectedSaved);
      setProfiles((items) =>
        items.filter((item) => item.id !== selectedSaved.id),
      );
      selectProfile(null);
      try {
        localStorage.removeItem(profileSelectionKey);
      } catch {
        /* Danh sách backend vẫn cập nhật. */
      }
    } catch (reason) {
      setManagementError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function undoDelete() {
    if (!lastDeleted || busy) return;
    setBusy(true);
    setManagementError("");
    try {
      const restored = await restoreCountingProfile(lastDeleted.id);
      setProfiles((items) => [...items, restored]);
      setLastDeleted(null);
    } catch (reason) {
      setManagementError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function openProfile(id: string) {
    selectProfile(profiles.find((item) => item.id === id) ?? null);
  }
  function selectProfile(profile: CountingProfile | null) {
    setWorkspaceDirty(false);
    setNewTouched(false);
    setManagementError("");
    setProfileId(profile?.id ?? null);
    if (profile) {
      try {
        localStorage.setItem(profileSelectionKey, profile.id);
      } catch {
        /* Có thể chọn lại cấu hình ở màn giám sát. */
      }
    }
    setInitialProfile(profile);
    let number = 1;
    while (
      profiles.some(
        (item) => item.name.toLocaleLowerCase() === `cấu hình ${number}`,
      )
    ) {
      number++;
    }
    setProfileName(profile?.name ?? `Cấu hình ${number}`);
    if (profile) {
      setSourceMode("saved");
      setSourceId(profile.source_id);
      setModelId(profile.monitor.model_id);
    }
    setStep(0);
    setEditorVersion((value) => value + 1);
  }
  const { confirmDiscard, ask, dialog } = useUnsavedChanges(
    configureOnly && (workspaceDirty || selectionDirty),
    () => selectProfile(selectedSaved ?? null),
  );
  function profileSaved(profile: CountingProfile) {
    setWorkspaceDirty(false);
    setNewTouched(false);
    setProfiles((items) => [
      ...items.filter((item) => item.id !== profile.id),
      profile,
    ]);
    setProfileId(profile.id);
    setProfileName(profile.name);
    try {
      localStorage.setItem(profileSelectionKey, profile.id);
    } catch {
      /* Chọn lại thủ công nếu không lưu được. */
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    async function loadSources(kind: "video" | "stream") {
      const items: VisionSource[] = [];
      let offset = 0,
        total = 1;
      while (offset < total) {
        const page = await listSources(offset, controller.signal, {
          kind,
          limit: 100,
        });
        items.push(...page.items);
        offset += page.items.length;
        total = page.total;
        if (!page.items.length) break;
      }
      return items;
    }
    async function load() {
      try {
        const [videos, cameras, library, savedProfiles] = await Promise.all([
          loadSources("video"),
          loadSources("stream"),
          getLibrary(controller.signal),
          listCountingProfiles(controller.signal),
        ]);
        if (controller.signal.aborted) return;
        const eligible = library.filter(
          (item) =>
            item.familyId.startsWith("yoloe") &&
            item.format === "pt" &&
            ["ready", "manual"].includes(item.inspection.status) &&
            ["detect", "segment"].includes(item.task ?? ""),
        );
        setProfiles(savedProfiles);
        setSources([...videos, ...cameras]);
        setModels(eligible);
        setError("");
        let selectedProfile: CountingProfile | undefined;
        try {
          selectedProfile = savedProfiles.find(
            (item) => item.id === localStorage.getItem(profileSelectionKey),
          );
        } catch {
          /* Lựa chọn lưu không bắt buộc. */
        }
        if (revision === 0 && selectedProfile) {
          setProfileId(selectedProfile.id);
          setInitialProfile(selectedProfile);
          setProfileName(selectedProfile.name);
        } else if (revision === 0) {
          let number = 1;
          while (
            savedProfiles.some(
              (item) => item.name.toLocaleLowerCase() === `cấu hình ${number}`,
            )
          )
            number++;
          setProfileName(`Cấu hình ${number}`);
        }
        let stored: { sourceId?: string; modelId?: string } = {};
        try {
          stored = JSON.parse(localStorage.getItem(selectionKey) ?? "{}");
        } catch {
          /* Dùng lựa chọn mới khi trình duyệt không có dữ liệu. */
        }
        setSourceId((current) =>
          revision === 0 && selectedProfile
            ? selectedProfile.source_id
            : [...videos, ...cameras].some((item) => item.id === current)
              ? current
              : [...videos, ...cameras].some(
                    (item) => item.id === stored.sourceId,
                  )
                ? stored.sourceId!
                : "",
        );
        setModelId((current) =>
          revision === 0 && selectedProfile
            ? selectedProfile.monitor.model_id
            : eligible.some((item) => item.id === current)
              ? current
              : eligible.some((item) => item.id === stored.modelId)
                ? stored.modelId!
                : (eligible.find((item) => item.id === "yoloe-26s-seg.pt")
                    ?.id ??
                  eligible[0]?.id ??
                  ""),
        );
      } catch (reason) {
        if (!controller.signal.aborted) setError((reason as Error).message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (loading) return;
    try {
      localStorage.setItem(selectionKey, JSON.stringify({ sourceId, modelId }));
    } catch {
      /* Không cản dùng khi localStorage bị chặn. */
    }
  }, [sourceId, modelId, loading]);
  const restoreModel = useCallback(
    (id: string) => setModelId(id),
    [setModelId],
  );
  const source = sources.find((item) => item.id === sourceId) ?? null;
  const model = models.find((item) => item.id === modelId) ?? null;
  const filteredSources = sources.filter(
    (item) =>
      (sourceFilter === "all" || item.kind === sourceFilter) &&
      item.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
  );
  async function upload() {
    if (!file || busy || locked) return;
    setBusy(true);
    setError("");
    try {
      const saved = await saveSource(
        {
          id: crypto.randomUUID(),
          name: fileName || file.name,
          kind: "video",
          location: "",
          status: "loading",
          file,
        },
        fileName || file.name,
      );
      setSources((items) => [saved, ...items]);
      setSourceId(saved.id);
      setSourceMode("saved");
      setFile(null);
      setFileName("");
      setNewTouched(true);
      toast.success("Đã thêm video.");
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <WorkspacePage
      title={configureOnly ? "Counting Configuration" : "Zone Counting"}
      description={
        configureOnly
          ? "Thiết lập nguồn, model và vùng đếm."
          : "Đếm hiện diện các class YOLOE trong vùng trên video hoặc camera RTSP."
      }
    >
      {dialog}
      {configureOnly && (
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="counting-profile">Cấu hình đã lưu</Label>
            <Select
              value={profileId ?? "new"}
              onValueChange={(id) => {
                if (id !== (profileId ?? "new"))
                  confirmDiscard(() => openProfile(id));
              }}
              disabled={locked || loading || busy}
            >
              <SelectTrigger id="counting-profile" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="new">+ Tạo cấu hình mới</SelectItem>
                  {profiles.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="counting-profile-name">Tên cấu hình</Label>
            <Input
              id="counting-profile-name"
              value={profileName}
              maxLength={100}
              disabled={locked || loading}
              onChange={(event) => {
                setNewTouched(true);
                setProfileName(event.target.value);
              }}
              placeholder="Ví dụ: Cấu hình 1"
            />
          </div>
          <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
            <Button
              disabled={
                locked || loading || busy || !source || !model ||
                sourceMode === "new" || !profileName.trim() ||
                (Boolean(profileId) && !workspaceDirty && !selectionDirty)
              }
              onClick={() => void editor.current?.save()}
            >
              <SaveIcon /> {locked ? "Đang xử lý…" : "Lưu cấu hình"}
            </Button>
            <span role="status" className="text-sm text-muted-foreground">
              {workspaceDirty || selectionDirty
                ? "Chưa lưu"
                : profileId ? "Đã lưu" : "Cấu hình mới"}
            </span>
            {profileId ? (
              <Button variant="outline" asChild>
                <Link href="/counting/monitor">
                  Mở giám sát
                  <ArrowRightIcon />
                </Link>
              </Button>
            ) : (
              <Button variant="outline" disabled>
                Mở giám sát
                <ArrowRightIcon />
              </Button>
            )}
            {profileId && (
              <>
                <Button
                  variant="outline"
                  disabled={locked || loading || busy}
                  onClick={() => confirmDiscard(() => void duplicateProfile())}
                >
                  <CopyIcon /> Nhân bản
                </Button>
                <Button
                  variant="destructive"
                  disabled={locked || loading || busy}
                  onClick={() =>
                    ask({
                      title: "Xoá cấu hình?",
                      description: `Xoá “${selectedSaved?.name ?? profileName}”. Bạn có thể hoàn tác sau khi xoá.`,
                      label: "Xoá cấu hình",
                      action: () => void removeProfile(),
                    })
                  }
                >
                  <Trash2Icon /> Xoá
                </Button>
              </>
            )}
          </div>
          {managementError && (
            <p role="alert" className="text-sm text-destructive sm:col-span-2">
              {managementError}
            </p>
          )}
          {lastDeleted && (
            <div
              role="status"
              className="flex flex-wrap items-center gap-3 text-sm sm:col-span-2"
            >
              Đã xoá “{lastDeleted.name}”.
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => void undoDelete()}
              >
                Hoàn tác
              </Button>
            </div>
          )}
        </div>
      )}
      <ol
        aria-label="Các bước thiết lập"
        className={`grid grid-cols-2 gap-3 ${configureOnly ? "sm:grid-cols-3" : "sm:grid-cols-4"}`}
      >
        {visibleSteps.map((title, index) => (
          <li
            key={title}
            aria-current={step === index ? "step" : undefined}
            className={`flex items-center gap-2 border-b-2 pb-3 text-sm ${step === index ? "border-primary font-semibold" : "border-border text-muted-foreground"}`}
          >
            <button
              type="button"
              className="flex w-full items-center gap-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy || loading || locked || (index > 0 && (!source || sourceMode === "new")) || (index > 1 && !model) || (!configureOnly && index > step)}
              onClick={() => setStep(index)}
            >
              <span className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs ${step === index ? "bg-primary text-primary-foreground" : "bg-muted"}`}>
                {step > index ? <CheckIcon className="size-3" /> : index + 1}
              </span>
              {title}
            </button>
          </li>
        ))}
      </ol>
      {step < 2 && (
        <WorkspaceSection
          title={steps[step]}
          titleId="counting-source-heading"
          actions={
            <>
              <Button
                variant="outline"
                disabled={step === 0 || busy || loading || locked}
                onClick={() => setStep(0)}
              >
                <ArrowLeftIcon /> Quay lại
              </Button>
              <Button
                disabled={
                  busy ||
                  loading ||
                  locked ||
                  (step === 0 ? !source || sourceMode === "new" : !model)
                }
                onClick={() => setStep(step + 1)}
              >
                Tiếp tục <ArrowRightIcon />
              </Button>
              <Button
                variant="outline"
                size="icon"
                aria-label="Làm mới danh sách"
                disabled={busy || locked}
                onClick={() => setRevision((value) => value + 1)}
              >
                <RefreshCwIcon />
              </Button>
            </>
          }
        >
          <div className="space-y-6">
            {step === 0 && (
              <div
                className="flex flex-wrap gap-2"
                role="group"
                aria-label="Cách chọn source"
              >
                <Button
                  variant={sourceMode === "new" ? "secondary" : "ghost"}
                  aria-pressed={sourceMode === "new"}
                  disabled={busy || locked}
                  onClick={() => setSourceMode("new")}
                >
                  <PlusIcon /> Nguồn mới
                </Button>
                <Button
                  variant={sourceMode === "saved" ? "secondary" : "ghost"}
                  aria-pressed={sourceMode === "saved"}
                  disabled={busy || locked}
                  onClick={() => setSourceMode("saved")}
                >
                  <BookmarkIcon /> Đã lưu ({sources.length})
                </Button>
              </div>
            )}
            {step === 1 && (
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" aria-pressed>
                  <BookmarkIcon /> Đã có ({models.length})
                </Button>
                <Button variant="ghost" asChild>
                  <Link href="/models">
                    <UploadIcon /> Thêm model
                  </Link>
                </Button>
              </div>
            )}
            <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
              <div className="min-w-0 space-y-6">
                {step === 0 && sourceMode === "saved" && (
                  <div className="space-y-6">
                    <div
                      className="flex flex-wrap gap-1.5"
                      role="group"
                      aria-label="Phân loại source đã lưu"
                    >
                      {[
                        ["all", "Tất cả"],
                        ["video", "Video"],
                        ["stream", "Camera RTSP"],
                      ].map(([value, label]) => (
                        <Button
                          key={value}
                          size="sm"
                          variant={
                            sourceFilter === value ? "secondary" : "ghost"
                          }
                          aria-pressed={sourceFilter === value}
                          onClick={() => setSourceFilter(value)}
                        >
                          {label}
                        </Button>
                      ))}
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="counting-source-search">Tìm nguồn</Label>
                      <div className="relative">
                        <SearchIcon className="absolute top-2.5 left-3 size-4 text-muted-foreground" />
                        <Input
                          className="h-9 pl-9"
                          maxLength={120}
                          id="counting-source-search"
                          value={search}
                          onChange={(event) => setSearch(event.target.value)}
                          placeholder="Tìm theo tên…"
                        />
                      </div>
                    </div>
                    <SavedSourceItems
                      items={filteredSources}
                      selectedId={sourceId}
                      disabled={busy || locked}
                      onSelect={(item) => {
                        if (item.id !== sourceId)
                          confirmDiscard(() => {
                            setNewTouched(true);
                            setSourceId(item.id);
                          });
                      }}
                    />
                    {!filteredSources.length && !loading && (
                      <p className="py-10 text-center text-sm text-muted-foreground">
                        {search
                          ? "Không tìm thấy nguồn."
                          : sourceFilter !== "all"
                            ? "Chưa có nguồn thuộc loại này."
                            : "Chưa có nguồn. Chọn Nguồn mới để thêm."}
                      </p>
                    )}
                    <div className="flex flex-wrap items-center gap-3">
                      <p className="text-xs text-muted-foreground">
                        {filteredSources.length}/{sources.length} source.
                      </p>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={loading || busy || locked}
                        onClick={() => setRevision((value) => value + 1)}
                      >
                        Làm mới
                      </Button>
                    </div>
                  </div>
                )}
                {step === 1 && (
                  <>
                    <ModelLibraryPicker
                      selection={{
                        library: models,
                        selectedId: modelId,
                        loading,
                        libraryError: error,
                        validating: locked || busy,
                        refresh: () => setRevision((value) => value + 1),
                        update: ({ selectedId }) => {
                          setNewTouched(true);
                          setModelId(selectedId);
                        },
                      }}
                    />
                  </>
                )}
                {step === 0 && sourceMode === "new" && !locked && (
                  <div className="space-y-6">
                    <div className="space-y-2">
                      <Label htmlFor="counting-new-source-kind">
                        Loại source
                      </Label>
                      <Select
                        value={newSourceKind}
                        disabled={busy}
                        onValueChange={(value) => {
                          setNewSourceKind(value);
                          setError("");
                        }}
                      >
                        <SelectTrigger
                          id="counting-new-source-kind"
                          className="w-full"
                        >
                          <SelectValue placeholder="Chọn loại nguồn" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectGroup>
                            <SelectItem value="video">Video file</SelectItem>
                            <SelectItem value="stream">Camera RTSP</SelectItem>
                          </SelectGroup>
                        </SelectContent>
                      </Select>
                    </div>
                    {newSourceKind === "video" && (
                      <form
                        className="space-y-4"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void upload();
                        }}
                      >
                        <VideoSourceInput
                          disabled={busy}
                          selection={{
                            source: file ? { file, status: "ready" } : null,
                            selectFile: (next) => {
                              setFile(next);
                              setFileName(next.name);
                            },
                          }}
                        />
                        <div className="space-y-2">
                          <Label htmlFor="counting-video-name">Tên video</Label>
                          <Input
                            id="counting-video-name"
                            value={fileName}
                            disabled={busy}
                            maxLength={120}
                            onChange={(event) =>
                              setFileName(event.target.value)
                            }
                          />
                        </div>
                        <Button
                          type="submit"
                          variant="outline"
                          disabled={!file || busy || !fileName.trim()}
                        >
                          <UploadIcon />
                          {busy ? "Đang lưu nguồn…" : "Lưu video và chọn"}
                        </Button>
                      </form>
                    )}
                    {newSourceKind === "stream" && (
                      <RtspCameraForm
                        busy={busy}
                        onSave={async (name, url) => {
                          if (busy) return false;
                          setBusy(true);
                          setError("");
                          try {
                            const saved = await configureRtspSource(name, url);
                            setSources((items) => [saved, ...items]);
                            setSourceId(saved.id);
                            setSourceMode("saved");
                            return true;
                          } catch (reason) {
                            setError((reason as Error).message);
                            return false;
                          } finally {
                            setBusy(false);
                          }
                        }}
                      />
                    )}
                  </div>
                )}
              </div>
              {step === 0 ? (
                <SourceDetails
                  source={sourceMode === "saved" ? source : null}
                  emptyKind={newSourceKind === "stream" ? "stream" : "video"}
                />
              ) : (
                <ModelDetails model={model} />
              )}
            </div>
            {loading && (
              <p role="status" className="text-sm text-muted-foreground">
                Đang tải nguồn và model…
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            {locked && (
              <p className="text-xs text-muted-foreground">
                {configureOnly
                  ? "Đang tải trạng thái hoặc lưu cấu hình…"
                  : "Dừng đếm và chọn Thiết lập lại để đổi nguồn, model hoặc vùng."}
              </p>
            )}
          </div>
        </WorkspaceSection>
      )}
      {source && (
        <div hidden={step < 2} className="space-y-8">
          <ZoneWorkspace
            ref={editor}
            key={`${editorVersion}:${source.id}`}
            source={source}
            model={model}
            onLock={setLocked}
            onRestoreModel={restoreModel}
            step={step}
            onStepChange={setStep}
            onRestoreRun={restoreRun}
            configureOnly={configureOnly}
            profileId={profileId}
            profileName={profileName}
            initialProfile={initialProfile}
            onProfileSaved={profileSaved}
            onDirtyChange={setWorkspaceDirty}
          />
        </div>
      )}
    </WorkspacePage>
  );
}
