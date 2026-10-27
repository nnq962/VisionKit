import type { SourceKind, VisionSource } from "./types";

export type SourceDraft = {
  source: VisionSource | null;
  location: string;
  name: string;
  save: boolean;
};
export type DraftSnapshot = {
  kind: SourceKind;
  drafts: Partial<Record<SourceKind, SourceDraft>>;
};

async function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("visionkit-source-drafts", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("drafts");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () =>
      reject(new Error("Không mở được bộ nhớ bản nháp."));
  });
}

export async function readDrafts(): Promise<DraftSnapshot | undefined> {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const request = db
        .transaction("drafts")
        .objectStore("drafts")
        .get("yolo");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally {
    db.close();
  }
}

export async function writeDrafts(snapshot: DraftSnapshot): Promise<void> {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("drafts", "readwrite");
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
      transaction.objectStore("drafts").put(snapshot, "yolo");
    });
  } finally {
    db.close();
  }
}

export function serializableDrafts(
  kind: SourceKind,
  drafts: DraftSnapshot["drafts"],
): DraftSnapshot {
  const snapshot: DraftSnapshot = { kind, drafts: {} };
  for (const [key, draft] of Object.entries(drafts)) {
    if (
      !draft ||
      draft.source?.saved ||
      (!draft.source && !draft.location.trim())
    )
      continue;
    const source = draft.source
      ? { ...draft.source, mediaStream: undefined, previewUrl: undefined }
      : null;
    if (source?.kind === "stream") source.streamPreview = false;
    if (source?.kind === "webcam" && source.status === "loading") source.status = "pending";
    snapshot.drafts[key as SourceKind] = { ...draft, source };
  }
  return snapshot;
}
