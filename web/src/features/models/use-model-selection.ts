"use client";

import type { ModelTask } from "./catalog";
import { useEffect, useRef, useState } from "react";
import {
  getCatalog,
  getLibrary,
  getModel,
  inspectModel,
  configureModel,
  uploadModel,
  saveTemporaryModel,
  deleteModel,
  releaseTemporaryModel,
  type StoredModel,
} from "./api";
import {
  emptyModelDraft,
  readModelDraft,
  writeModelDraft,
  type ModelDraft,
} from "./model-draft-storage";

export function useModelSelectionState() {
  const [draft, setDraft] = useState<ModelDraft>(emptyModelDraft);
  const [draftsReady, setDraftsReady] = useState(false);
  const [draftStored, setDraftStored] = useState(false);
  const [temporary, setTemporary] = useState<StoredModel | null>(null);
  const [saving, setSaving] = useState(false);
  const attemptedFile = useRef<File | null>(null);
  const [library, setLibrary] = useState<StoredModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [libraryError, setLibraryError] = useState("");
  const [error, setError] = useState("");
  const [draftError, setDraftError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [validating, setValidating] = useState(false);
  const [inspecting, setInspecting] = useState(false);
  const metadataBusy = useRef(false);
  const [maxBytes, setMaxBytes] = useState(200 * 1024 * 1024);
  const [revision, setRevision] = useState(0);
  const storageQueue = useRef(Promise.resolve());
  const current = useRef(draft);
  const upload = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const checking = useRef(false);

  useEffect(() => {
    mounted.current = true;
    let active = true;
    readModelDraft()
      .then((saved) => {
        if (!active) return;
        if (
          saved &&
          ["saved", "upload"].includes(saved.mode) &&
          ["yolo", "yoloe"].includes(saved.family) &&
          ["detect", "segment", "classify", "pose", "obb"].includes(saved.task)
        ) {
          const restored = { ...emptyModelDraft, ...saved };
          current.current = restored;
          setDraft(restored);
        }
      })
      .catch(() => {
        if (active) setDraftError("Không khôi phục được nháp model.");
      })
      .finally(() => {
        if (active) setDraftsReady(true);
      });
    return () => {
      active = false;
      mounted.current = false;
      upload.current?.abort();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getLibrary(controller.signal), getCatalog(controller.signal)])
      .then(([items, catalog]) => {
        if (controller.signal.aborted) return;
        setLibrary(items);
        setMaxBytes(catalog.max_upload_bytes);
        setLibraryError("");
      })
      .catch((reason: Error) => {
        if (!controller.signal.aborted) setLibraryError(reason.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    if (!draftsReady) return;
    let active = true;
    const timer = setTimeout(() => {
      storageQueue.current = storageQueue.current
        .catch(() => {})
        .then(() => writeModelDraft(draft));
      storageQueue.current
        .then(() => {
          if (active) {
            setDraftStored(true);
            setDraftError("");
          }
        })
        .catch(() => {
          if (active) {
            setDraftStored(false);
            setDraftError("Không giữ được nháp qua reload.");
          }
        });
    }, 150);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [draft, draftsReady]);

  useEffect(() => {
    if (!uploading && (!draft.file || draftStored)) return;
    function beforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [uploading, draft.file, draftStored]);

  useEffect(() => {
    const changed = () => {
      setLoading(true);
      setRevision((value) => value + 1);
    };
    window.addEventListener("visionkit:models-changed", changed);
    window.addEventListener("focus", changed);
    return () => {
      window.removeEventListener("visionkit:models-changed", changed);
      window.removeEventListener("focus", changed);
    };
  }, []);

  function replaceModel(model: StoredModel) {
    if (current.current.temporaryId === model.id) setTemporary(model);
    setLibrary((items) =>
      items.map((item) => (item.id === model.id ? model : item)),
    );
  }

  useEffect(() => {
    if (!draftsReady || !draft.temporaryId) return;
    const controller = new AbortController();
    getModel(draft.temporaryId, controller.signal)
      .then((model) => {
        if (!controller.signal.aborted) setTemporary(model);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setError((reason as Error).message);
      });
    return () => controller.abort();
  }, [draftsReady, draft.temporaryId]);

  useEffect(() => {
    if (
      !draftsReady ||
      !draft.file ||
      draft.temporaryId ||
      attemptedFile.current === draft.file
    )
      return;
    attemptedFile.current = draft.file;
    void stage();
    // A restored draft uploads once; explicit retry handles failures.
  }, [draftsReady, draft.file, draft.temporaryId]);

  const selected =
    draft.mode === "upload"
      ? temporary
      : (library.find((item) => item.id === draft.selectedId) ?? null);
  const inspectionStatus = selected?.inspection.status;
  useEffect(() => {
    const id = selected?.id;
    if (
      !id ||
      !inspectionStatus ||
      !["uninspected", "queued", "processing"].includes(inspectionStatus)
    )
      return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const model =
          inspectionStatus === "uninspected"
            ? await inspectModel(id!, controller.signal)
            : await getModel(id!, controller.signal);
        if (controller.signal.aborted) return;
        replaceModel(model);
      } catch (reason) {
        if (!controller.signal.aborted) setError((reason as Error).message);
      }
      if (!controller.signal.aborted)
        timer = setTimeout(() => void poll(), 1500);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [selected?.id, inspectionStatus]);

  async function retryInspection() {
    const id =
      current.current.mode === "upload"
        ? current.current.temporaryId
        : current.current.selectedId;
    if (!id || metadataBusy.current) return;
    metadataBusy.current = true;
    setInspecting(true);
    setError("");
    try {
      const model = await inspectModel(id);
      if (mounted.current) replaceModel(model);
    } catch (reason) {
      if (mounted.current) setError((reason as Error).message);
    } finally {
      metadataBusy.current = false;
      if (mounted.current) setInspecting(false);
    }
  }
  async function configure(
    family: "yolo" | "yoloe",
    task: ModelTask,
  ): Promise<boolean> {
    const id =
      current.current.mode === "upload"
        ? current.current.temporaryId
        : current.current.selectedId;
    if (!id || metadataBusy.current) return false;
    metadataBusy.current = true;
    setInspecting(true);
    setError("");
    try {
      const model = await configureModel(id, family, task);
      if (mounted.current) replaceModel(model);
      return true;
    } catch (reason) {
      if (mounted.current) setError((reason as Error).message);
      return false;
    } finally {
      metadataBusy.current = false;
      if (mounted.current) setInspecting(false);
    }
  }

  function update(patch: Partial<ModelDraft>) {
    if (upload.current) return;
    const next = { ...current.current, ...patch };
    current.current = next;
    setDraft(next);
    setDraftStored(false);
    setError("");
  }
  function refresh() {
    setLoading(true);
    setRevision((value) => value + 1);
  }
  function chooseFile(file: File) {
    if (!/\.(pt|onnx)$/i.test(file.name)) {
      setError("Chọn tệp .pt hoặc .onnx.");
      return;
    }
    if (!file.size) {
      setError("Tệp model đang rỗng.");
      return;
    }
    if (file.size > maxBytes) {
      setError(
        `Model vượt giới hạn ${Math.floor(maxBytes / (1024 * 1024))} MB.`,
      );
      return;
    }
    const previous = current.current.temporaryId;
    setTemporary(null);
    if (previous) void deleteModel(previous).catch(() => {});
    update({
      file,
      temporaryId: null,
      name: (file.name.replace(/\.(pt|onnx)$/i, "") || file.name).slice(0, 120),
    });
    setProgress(0);
  }
  async function stage() {
    const value = current.current;
    if (upload.current || !value.file || !value.name.trim()) return;
    const controller = new AbortController();
    upload.current = controller;
    setUploading(true);
    setProgress(0);
    setError("");
    try {
      const saved = await uploadModel(
        {
          file: value.file,
          name: value.name,
        },
        controller.signal,
        (value) => {
          if (mounted.current) setProgress(value);
        },
      );
      if (!mounted.current) return;
      const next = { ...current.current, temporaryId: saved.id };
      current.current = next;
      setDraft(next);
      setDraftStored(false);
      setTemporary(saved);
    } catch (reason) {
      if (mounted.current)
        setError(
          (reason as Error).name === "AbortError"
            ? ""
            : (reason as Error).message,
        );
    } finally {
      upload.current = null;
      if (mounted.current) setUploading(false);
    }
  }
  async function save() {
    const value = current.current;
    if (
      !value.temporaryId ||
      saving ||
      metadataBusy.current ||
      !value.name.trim()
    )
      return;
    setSaving(true);
    setError("");
    try {
      const saved = await saveTemporaryModel(
        value.temporaryId,
        value.name.trim(),
      );
      if (!mounted.current) return;
      const next = {
        ...current.current,
        file: null,
        name: "",
        mode: "saved" as const,
        selectedId: saved.id,
        temporaryId: null,
      };
      current.current = next;
      setDraft(next);
      setTemporary(null);
      setLibrary((items) => [
        saved,
        ...items.filter((item) => item.id !== saved.id),
      ]);
      window.dispatchEvent(new Event("visionkit:models-changed"));
    } catch (reason) {
      if (mounted.current) setError((reason as Error).message);
    } finally {
      if (mounted.current) setSaving(false);
    }
  }
  async function validate(): Promise<StoredModel | null> {
    if (checking.current) return null;
    const id =
      current.current.mode === "upload"
        ? current.current.temporaryId
        : current.current.selectedId;
    if (!id) {
      setError("Chọn một model trong thư viện.");
      return null;
    }
    checking.current = true;
    setValidating(true);
    setError("");
    try {
      const model = await getModel(id);
      if (!["ready", "manual"].includes(model.inspection.status)) {
        if (mounted.current) {
          replaceModel(model);
          setError(
            "Đọc metadata hoặc bổ sung thông tin model trước khi tiếp tục.",
          );
        }
        return null;
      }
      if (!mounted.current) return null;
      replaceModel(model);
      return model;
    } catch (reason) {
      if (mounted.current) {
        setError((reason as Error).message);
        refresh();
      }
      return null;
    } finally {
      checking.current = false;
      if (mounted.current) setValidating(false);
    }
  }
  return {
    ...draft,
    library,
    loading,
    libraryError,
    error,
    draftError,
    draftsReady,
    uploading,
    saving,
    stage,
    progress,
    validating,
    maxBytes,
    selected,
    inspecting,
    retryInspection,
    configure,
    update,
    chooseFile,
    refresh,
    save,
    validate,
    cancel() {
      upload.current?.abort();
    },
    async finishTemporary() {
      const id = current.current.temporaryId;
      if (!id || selected?.id !== id || !selected.expiresAt) return () => {};
      await releaseTemporaryModel(id);
      return () => {
        setTemporary(null);
        update({ file: null, name: "", temporaryId: null });
        setProgress(0);
      };
    },
    discard() {
      const id = current.current.temporaryId;
      setTemporary(null);
      update({ file: null, name: "", temporaryId: null });
      if (id) void deleteModel(id).catch(() => {});
      setProgress(0);
    },
  };
}
export type ModelSelection = ReturnType<typeof useModelSelectionState>;
