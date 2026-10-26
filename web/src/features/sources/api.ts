import type { SourceKind, VisionSource } from "./types";

const base = "/api/v1/sources";

type SourceRecord = {
  id: string;
  name: string;
  kind: SourceKind;
  location: string;
  metadata: Record<string, unknown>;
  content_url: string | null;
  preview_url: string | null;
  created_at: string;
  updated_at?: string;
};

type SourcePage = {
  items: SourceRecord[];
  total: number;
  limit: number;
  offset: number;
};

function fromRecord(record: SourceRecord): VisionSource {
  const number = (key: string) =>
    typeof record.metadata[key] === "number"
      ? (record.metadata[key] as number)
      : undefined;
  return {
    id: record.id,
    name: record.name,
    kind: record.kind,
    location: record.location,
    status: ["image", "screen", "video"].includes(record.kind)
      ? "ready"
      : "pending",
    saved: true,
    createdAt: record.created_at,
    updatedAt: record.updated_at,
    originalFilename:
      typeof record.metadata.original_filename === "string"
        ? record.metadata.original_filename
        : undefined,
    mimeType:
      typeof record.metadata.mime_type === "string"
        ? record.metadata.mime_type
        : undefined,
    sha256:
      typeof record.metadata.sha256 === "string"
        ? record.metadata.sha256
        : undefined,
    previewLocation:
      typeof record.metadata.preview_location === "string"
        ? record.metadata.preview_location
        : undefined,
    previewSize: number("preview_size"),
    previewUrl:
      (record.kind === "video"
        ? record.content_url
        : (record.preview_url ?? record.content_url)) ?? undefined,
    thumbnailUrl:
      record.kind === "video" ? (record.preview_url ?? undefined) : undefined,
    width: number("width"),
    height: number("height"),
    size: number("size"),
    duration: number("duration"),
    fps: number("fps"),
    format:
      typeof record.metadata.format === "string"
        ? record.metadata.format
        : undefined,
  };
}

async function send(path: string, options?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, { cache: "no-store", ...options });
  } catch {
    throw new Error("Không kết nối được backend. Kiểm tra server rồi thử lại.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : Array.isArray(body?.detail)
          ? "Dữ liệu chưa hợp lệ. Kiểm tra thông tin đã nhập."
          : "Không kết nối được API. Kiểm tra backend rồi thử lại.";
    throw new Error(message);
  }
  return response;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await send(path, options);
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function listSources(
  offset = 0,
  signal?: AbortSignal,
  filters?: { q?: string; kind?: SourceKind; limit?: number },
) {
  const params = new URLSearchParams({
    limit: String(filters?.limit ?? 50),
    offset: String(offset),
  });
  if (filters?.q) params.set("q", filters.q);
  if (filters?.kind) params.set("kind", filters.kind);
  const page = await request<SourcePage>(`?${params}`, {
    signal,
  });
  return { ...page, items: page.items.map(fromRecord) };
}

export async function saveSource(
  source: VisionSource,
  name: string,
): Promise<VisionSource> {
  if (source.saved) return renameSource(source.id, name);
  if (!source.file || !["image", "screen", "video"].includes(source.kind))
    throw new Error("Loại source này chưa hỗ trợ lưu.");
  const body = new FormData();
  body.set("file", source.file);
  body.set("name", name);
  body.set("kind", source.kind);
  return fromRecord(
    await request<SourceRecord>("/upload", { method: "POST", body }),
  );
}

export async function renameSource(id: string, name: string) {
  return fromRecord(
    await request<SourceRecord>(`/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  );
}

export async function deleteSource(id: string) {
  await request<void>(`/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function inspectImage(file: File) {
  const body = new FormData();
  body.set("file", file);
  const response = await send("/inspect", { method: "POST", body });
  return {
    blob: await response.blob(),
    width: Number(response.headers.get("X-Image-Width")),
    height: Number(response.headers.get("X-Image-Height")),
    format: response.headers.get("X-Image-Format") ?? "HEIC",
  };
}

export async function configureRtspSource(name: string, url: string, id?: string) {
  return fromRecord(await request<SourceRecord>(id ? `/${encodeURIComponent(id)}/rtsp` : "/rtsp", {
    method: id ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, url }),
  }));
}

export async function getSource(id: string) {
  return fromRecord(await request<SourceRecord>(`/${encodeURIComponent(id)}`));
}
