import type { ModelTask } from "./catalog";

export type ModelDraft = {
  mode: "saved" | "upload";
  selectedId: string | null;
  file: File | null;
  name: string;
  family: "yolo" | "yoloe";
  task: ModelTask;
};
export const emptyModelDraft: ModelDraft = {
  mode: "saved",
  selectedId: null,
  file: null,
  name: "",
  family: "yolo",
  task: "detect",
};
async function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("visionkit-model-drafts", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("drafts");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () =>
      reject(new Error("Không mở được bộ nhớ bản nháp model."));
  });
}
export async function readModelDraft(): Promise<ModelDraft | undefined> {
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
export async function writeModelDraft(draft: ModelDraft): Promise<void> {
  const db = await database();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction("drafts", "readwrite");
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
      transaction.onabort = () => reject(transaction.error);
      transaction.objectStore("drafts").put(draft, "yolo");
    });
  } finally {
    db.close();
  }
}
