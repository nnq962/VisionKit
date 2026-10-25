"use client";

import { useEffect, useRef, useState } from "react";
import {
  readDrafts,
  serializableDrafts,
  writeDrafts,
  type SourceDraft,
  type DraftSnapshot,
} from "./draft-storage";
import { sourceKinds, type SourceKind, type VisionSource } from "./types";

type Picker = DraftSnapshot & {
  mode: "new" | "saved";
  selected: VisionSource | null;
};
const initial: Picker = {
  mode: "new",
  kind: "image",
  drafts: {},
  selected: null,
};
const emptyDraft = (): SourceDraft => ({
  source: null,
  location: "",
  name: "",
  save: false,
});

export function useSourceDrafts() {
  const [picker, setPicker] = useState(initial);
  const current = useRef(picker);
  const revision = useRef(0);
  const writes = useRef<Promise<void>>(Promise.resolve());
  const [hydrated, setHydrated] = useState(false);
  const [storageStatus, setStorageStatus] = useState<
    "loading" | "saving" | "ready" | "error"
  >("loading");
  const restoredUrls = useRef(new Set<string>());

  function commit(update: (state: Picker) => Picker) {
    const next = update(current.current);
    if (next === current.current) return;
    revision.current++;
    current.current = next;
    setPicker(next);
    setStorageStatus("saving");
  }

  useEffect(() => {
    let cancelled = false;
    const start = revision.current;
    const urls = restoredUrls.current;
    readDrafts()
      .then((snapshot) => {
        if (cancelled) return;
        if (snapshot && revision.current === start) {
          const drafts: Picker["drafts"] = {};
          for (const { value: kind } of sourceKinds) {
            const draft = snapshot.drafts?.[kind];
            if (!draft) continue;
            const source = draft.source ? { ...draft.source } : null;
            if (source?.file && source.status === "loading") {
              source.status = "error";
              source.error =
                "Tệp được giữ lại nhưng chưa đọc xong. Bấm Đọc lại tệp để tiếp tục.";
            }
            const preview = source?.previewBlob ?? source?.file;
            if (source && preview && source.status === "ready") {
              source.previewUrl = URL.createObjectURL(preview);
              urls.add(source.previewUrl);
            }
            drafts[kind] = { ...draft, source };
          }
          const kind = drafts[snapshot.kind]
            ? snapshot.kind
            : (sourceKinds.find((item) => drafts[item.value])?.value ??
              "image");
          const next: Picker = { ...initial, drafts, kind };
          current.current = next;
          setPicker(next);
        }
        setHydrated(true);
        setStorageStatus("ready");
      })
      .catch(() => {
        if (!cancelled) {
          setHydrated(true);
          setStorageStatus("error");
        }
      });
    return () => {
      cancelled = true;
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.clear();
    };
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    const snapshot = serializableDrafts(picker.kind, picker.drafts);
    const version = revision.current;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      // Serialize writes so an older snapshot can never overwrite a newer one.
      writes.current = writes.current
        .catch(() => {})
        .then(() => writeDrafts(snapshot));
      void writes.current
        .then(() => {
          if (!cancelled && version === revision.current)
            setStorageStatus("ready");
        })
        .catch(() => {
          if (!cancelled && version === revision.current)
            setStorageStatus("error");
        });
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [picker, hydrated]);

  const draft = picker.drafts[picker.kind] ?? emptyDraft();
  const source = picker.mode === "new" ? draft.source : picker.selected;
  const draftCount = Object.values(picker.drafts).filter(
    (item) =>
      item && ((!item.source?.saved && item.source) || item.location.trim()),
  ).length;

  useEffect(() => {
    if (!draftCount || storageStatus === "ready") return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draftCount, storageStatus]);

  function editDraft(update: (draft: SourceDraft) => SourceDraft) {
    commit((state) => ({
      ...state,
      drafts: {
        ...state.drafts,
        [state.kind]: update(state.drafts[state.kind] ?? emptyDraft()),
      },
    }));
  }

  function begin(source: VisionSource) {
    commit((state) => ({
      ...state,
      mode: "new",
      kind: source.kind,
      drafts: {
        ...state.drafts,
        [source.kind]: {
          source,
          name: source.name,
          save: false,
          location:
            source.kind === "stream" || source.kind === "youtube"
              ? source.location
              : "",
        },
      },
    }));
  }

  function publish(source: VisionSource) {
    commit((state) => {
      const draft = state.drafts[source.kind];
      if (draft?.source?.id !== source.id) return state;
      return {
        ...state,
        drafts: {
          ...state.drafts,
          [source.kind]: {
            ...draft,
            source,
            name: draft.name === draft.source?.name ? source.name : draft.name,
          },
        },
      };
    });
  }

  function applySaved(previousId: string, source: VisionSource | null) {
    commit((state) => {
      const drafts = { ...state.drafts };
      for (const { value: kind } of sourceKinds) {
        if (drafts[kind]?.source?.id === previousId)
          drafts[kind] = {
            ...drafts[kind]!,
            source,
            name: source?.name ?? "",
            save: false,
            location: "",
          };
      }
      return {
        ...state,
        drafts,
        selected: state.selected?.id === previousId ? source : state.selected,
      };
    });
  }

  function discardDraft() {
    commit((state) => ({
      ...state,
      drafts: { ...state.drafts, [state.kind]: emptyDraft() },
    }));
  }

  return {
    source,
    draftsReady: hydrated,
    mode: picker.mode,
    kind: picker.kind,
    location: draft.location,
    saveName: picker.mode === "new" ? draft.name : (source?.name ?? ""),
    saveEnabled: picker.mode === "new" && draft.save,
    draftCount,
    storageStatus,
    begin,
    publish,
    applySaved,
    discardDraft,
    resumeDraft: () =>
      commit((state) => {
        const hasDraft = (draft?: SourceDraft) =>
          draft &&
          ((draft.source && !draft.source.saved) || draft.location.trim());
        const kind = hasDraft(state.drafts[state.kind])
          ? state.kind
          : (sourceKinds.find((item) => hasDraft(state.drafts[item.value]))
              ?.value ?? state.kind);
        return { ...state, mode: "new", kind };
      }),
    isCurrent: (source: VisionSource) =>
      current.current.drafts[source.kind]?.source?.id === source.id,
    select: (source: VisionSource | null) =>
      commit((state) =>
        state.mode === "saved"
          ? { ...state, selected: source }
          : {
              ...state,
              drafts: {
                ...state.drafts,
                [state.kind]: {
                  ...(state.drafts[state.kind] ?? emptyDraft()),
                  source,
                },
              },
            },
      ),
    setMode: (mode: Picker["mode"]) => commit((state) => ({ ...state, mode })),
    setKind: (kind: SourceKind) => commit((state) => ({ ...state, kind })),
    setSaveName: (name: string) => editDraft((draft) => ({ ...draft, name })),
    setSaveEnabled: (save: boolean) =>
      editDraft((draft) => ({ ...draft, save })),
    setLocation: (location: string) =>
      editDraft((draft) => ({ ...draft, location, source: null })),
  };
}
