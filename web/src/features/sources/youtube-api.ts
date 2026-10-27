import type { VisionSource } from "./types.ts";

export type YoutubeSession = {
  id: string;
  url: string;
  title: string;
  status: "queued" | "preparing" | "ready" | "failed" | "cancelled";
  error: string | null;
  metadata: { width?: number; height?: number; duration?: number; fps?: number; size?: number };
};
const base = "/api/v1/youtube/sessions";
async function request(path: string, options?: RequestInit): Promise<YoutubeSession> {
  const response = await fetch(base + path, { cache: "no-store", ...options });
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Không chuẩn bị được video YouTube.");
  return body;
}
export const createYoutube = (url: string) => request("", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }),
});
export const getYoutube = (id: string, signal?: AbortSignal) => request(`/${encodeURIComponent(id)}`, { signal });
export async function deleteYoutube(id: string) {
  const response = await fetch(`${base}/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!response.ok) throw new Error("Không xoá được video tạm. Thử lại.");
}
export function youtubePreview(id: string) {
  return `${base}/${encodeURIComponent(id)}/content`;
}
export function applyYoutube(source: VisionSource, job: YoutubeSession): VisionSource {
  return {
    ...source,
    youtubeSession: job.id,
    name: job.title,
    location: job.url,
    status: job.status === "ready" ? "ready" : ["failed", "cancelled"].includes(job.status) ? "error" : "loading",
    error: job.error ?? undefined,
    ...job.metadata,
    previewUrl: job.status === "ready" ? youtubePreview(job.id) : undefined,
    thumbnailUrl: job.status === "ready" ? `${base}/${encodeURIComponent(job.id)}/thumbnail` : undefined,
    format: "YouTube · MP4",
  };
}
