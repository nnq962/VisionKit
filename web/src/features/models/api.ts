import type { ModelFamily, ModelTask, ModelVariant } from "./catalog";

export type ModelMetadata = {
  format: "pt" | "onnx";
  family: "yolo" | "yoloe" | null;
  task: ModelTask | null;
  names: Record<string, string>;
  class_count: number | null;
  imgsz: number[] | null;
  input_shape: (number | string | null)[] | null;
  stride: number | null;
  model_type: string | null;
  model_series?: string | null;
  series_source?: "checkpoint_yaml" | "onnx_metadata" | null;
  ultralytics_version?: string | null;
  scale: string | null;
  parameters: number | null;
  producer: string | null;
  version: string | null;
};
export type ModelInspection = {
  status:
    | "uninspected"
    | "queued"
    | "processing"
    | "ready"
    | "needs_input"
    | "failed"
    | "unavailable"
    | "manual";
  metadata: ModelMetadata | null;
  message: string | null;
};
export type StoredModel = ModelVariant & {
  savedAt: string;
  expiresAt: string | null;
  sizeBytes: number;
  sha256: string;
  location: string;
  inspection: ModelInspection;
};
export type DownloadStatus =
  "queued" | "downloading" | "completed" | "failed" | "cancelled";
export type ModelDownload = {
  jobId: string;
  variant: ModelVariant;
  progress: number;
  received: number;
  total: number;
  status: DownloadStatus;
  error: string | null;
};
type DownloadRecord = {
  id: string;
  variant: ModelVariant;
  progress: number;
  downloaded_bytes: number;
  total_bytes: number;
  status: DownloadStatus;
  error: string | null;
};
export type Catalog = {
  release: string;
  families: ModelFamily[];
  variants: ModelVariant[];
  max_upload_bytes: number;
};
const base = "/api/v1/models";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, { cache: "no-store", ...options });
  } catch (error) {
    if (options?.signal?.aborted) throw error;
    throw new Error("Không kết nối được backend. Hãy thử lại.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : "Không thực hiện được thao tác. Hãy thử lại.",
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
function fromJob(job: DownloadRecord): ModelDownload {
  return {
    jobId: job.id,
    variant: job.variant,
    progress: job.progress,
    received: job.downloaded_bytes,
    total: job.total_bytes,
    status: job.status,
    error: job.error,
  };
}
export async function getCatalog(signal?: AbortSignal) {
  return request<Catalog>("/catalog", { signal });
}
type ModelRecord = {
  inspection: ModelInspection;
  id: string;
  variant: ModelVariant;
  saved_at: string;
  expires_at: string | null;
  size_bytes: number;
  sha256: string;
  location: string;
};
function fromModel(item: ModelRecord): StoredModel {
  return {
    ...item.variant,
    id: item.id,
    savedAt: item.saved_at,
    expiresAt: item.expires_at,
    sizeBytes: item.size_bytes,
    sha256: item.sha256,
    location: item.location,
    inspection: item.inspection,
  };
}
export async function getLibrary(signal?: AbortSignal): Promise<StoredModel[]> {
  const data = await request<{ items: ModelRecord[] }>("", { signal });
  return data.items.map(fromModel);
}
export async function getModel(id: string, signal?: AbortSignal) {
  return fromModel(
    await request<ModelRecord>(`/${encodeURIComponent(id)}`, { signal }),
  );
}
export type ModelUpload = {
  file: File;
  name: string;
  family?: "yolo" | "yoloe";
  task?: ModelTask;
};
export function uploadModel(
  data: ModelUpload,
  signal: AbortSignal,
  onProgress: (value: number) => void,
): Promise<StoredModel> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const body = new FormData();
    body.set("file", data.file);
    body.set("name", data.name.trim());
    if (data.family) body.set("family", data.family);
    if (data.task) body.set("task", data.task);
    const abort = () => xhr.abort();
    const cleanup = () => signal.removeEventListener("abort", abort);
    xhr.open("POST", `${base}/temporary`);
    xhr.timeout = 15 * 60 * 1000;
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress(
          Math.min(100, Math.floor((event.loaded / event.total) * 100)),
        );
    };
    xhr.onload = () => {
      cleanup();
      let result;
      try {
        result = JSON.parse(xhr.responseText);
      } catch {
        reject(new Error("Không đọc được phản hồi upload. Hãy thử lại."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(
          new Error(
            typeof result.detail === "string"
              ? result.detail
              : "Không lưu được model. Hãy thử lại.",
          ),
        );
        return;
      }
      resolve(fromModel(result));
    };
    xhr.onerror = () => {
      cleanup();
      reject(new Error("Mất kết nối khi upload. Hãy thử lại."));
    };
    xhr.ontimeout = () => {
      cleanup();
      reject(new Error("Upload quá thời gian chờ. Hãy thử lại."));
    };
    xhr.onabort = () => {
      cleanup();
      reject(new DOMException("Đã huỷ tải lên.", "AbortError"));
    };
    if (signal.aborted) {
      reject(new DOMException("Đã huỷ tải lên.", "AbortError"));
      return;
    }
    signal.addEventListener("abort", abort, { once: true });
    xhr.send(body);
  });
}
export async function getDownloads(signal?: AbortSignal) {
  const data = await request<{ items: DownloadRecord[] }>("/downloads", {
    signal,
  });
  return data.items.map(fromJob);
}
export async function startDownload(variant: ModelVariant) {
  return fromJob(
    await request<DownloadRecord>("/downloads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ catalog_id: variant.id }),
    }),
  );
}
export async function cancelDownload(id: string) {
  return fromJob(
    await request<DownloadRecord>(`/downloads/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  );
}
export async function deleteModel(id: string) {
  return request<void>(`/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function inspectModel(id: string, signal?: AbortSignal) {
  return fromModel(
    await request<ModelRecord>(`/${encodeURIComponent(id)}/inspect`, {
      method: "POST",
      signal,
    }),
  );
}
export async function configureModel(
  id: string,
  family: "yolo" | "yoloe",
  task: ModelTask,
) {
  return fromModel(
    await request<ModelRecord>(`/${encodeURIComponent(id)}/metadata`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ family, task }),
    }),
  );
}

export async function saveTemporaryModel(id: string, name: string) {
  return fromModel(
    await request<ModelRecord>(`/${encodeURIComponent(id)}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  );
}

/** Cleanup retry succeeds when a temporary model was already deleted. */
export async function releaseTemporaryModel(id: string) {
  const response = await fetch(`${base}/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (response.ok || response.status === 404 || response.status === 410) return;
  const body = await response.json().catch(() => null);
  throw new Error(typeof body?.detail === "string" ? body.detail : "Chưa dọn được model tạm. Bấm Hoàn thành để thử lại.");
}
