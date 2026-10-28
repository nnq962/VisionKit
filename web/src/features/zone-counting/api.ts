import type {
  CountingProfile,
  CountingConfig,
  CountingRun,
  SourceConfig,
  MonitorSettings,
} from "./types";

async function request<T>(
  path: string,
  options?: RequestInit,
  base = "/api/v1/counting",
): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    cache: "no-store",
    ...options,
  });
  const body = await response.json();
  if (!response.ok)
    throw Object.assign(
      new Error(
        typeof body.detail === "string"
          ? body.detail
          : "Cấu hình chưa hợp lệ. Kiểm tra polygon và các trường đã nhập.",
      ),
      { status: response.status },
    );
  return body;
}
export const getCountingConfig = (sourceId: string, signal?: AbortSignal) =>
  request<SourceConfig>(`/sources/${encodeURIComponent(sourceId)}`, { signal });
export const saveCountingConfig = (
  sourceId: string,
  signature: string,
  config: CountingConfig,
  monitor?: MonitorSettings,
) =>
  request<SourceConfig>(`/sources/${encodeURIComponent(sourceId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_signature: signature,
      config,
      ...(monitor ? { monitor } : {}),
    }),
  });
export function startCountingRun(
  sourceId: string,
  modelId: string,
  signature: string,
  config: CountingConfig,
  options: { conf: number; iou: number; device: string; max_fps: number },
  minutes: number,
) {
  return request<CountingRun>("/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_id: sourceId,
      model_id: modelId,
      source_signature: signature,
      config,
      options,
      duration_seconds: minutes * 60,
    }),
  });
}

export const getCountingRun = (id: string, signal?: AbortSignal) =>
  request<CountingRun>(
    `/${encodeURIComponent(id)}`,
    { signal },
    "/api/v1/runs",
  );

export const listCountingProfiles = (signal?: AbortSignal) =>
  request<CountingProfile[]>("/profiles", { signal });
export const getCountingProfile = (id: string, signal?: AbortSignal) =>
  request<CountingProfile>(`/profiles/${encodeURIComponent(id)}`, { signal });
export function saveCountingProfile(
  id: string | null,
  body: {
    name: string;
    source_id: string;
    source_signature: string;
    config: CountingConfig;
    monitor: MonitorSettings;
  },
) {
  return request<CountingProfile>(
    id ? `/profiles/${encodeURIComponent(id)}` : "/profiles",
    {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}
export const startCountingProfile = (id: string) =>
  request<CountingRun>(`/profiles/${encodeURIComponent(id)}/runs`, {
    method: "POST",
  });

export const stopCountingProfile = (id: string) =>
  request<CountingProfile>(`/profiles/${encodeURIComponent(id)}/stop`, {
    method: "POST",
  });
export const duplicateCountingProfile = (id: string) =>
  request<CountingProfile>(`/profiles/${encodeURIComponent(id)}/duplicate`, {
    method: "POST",
  });
export const deleteCountingProfile = (id: string) =>
  request<{ id: string }>(`/profiles/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
export const restoreCountingProfile = (id: string) =>
  request<CountingProfile>(`/profiles/${encodeURIComponent(id)}/restore`, {
    method: "POST",
  });
