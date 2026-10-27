import test from "node:test";
import assert from "node:assert/strict";
import { applyYoutube, youtubePreview } from "../src/features/sources/youtube-api.ts";
import { startRun } from "../src/features/inference/api.ts";
import { restoreRun } from "../src/features/inference/restore-run.ts";

const source = { id: "draft", kind: "youtube", status: "loading", name: "YouTube", location: "https://youtu.be/jNQXAC9IVRw" };
const job = { id: "a".repeat(32), title: "Video", url: "https://www.youtube.com/watch?v=jNQXAC9IVRw", status: "ready", error: null, metadata: { width: 320, height: 240, duration: 19 } };

test("prepared YouTube uses internal preview and metadata without signed media URLs", () => {
  const ready = applyYoutube(source, job);
  assert.equal(ready.status, "ready");
  assert.equal(ready.name, "Video");
  assert.equal(ready.width, 320);
  assert.equal(ready.youtubeSession, job.id);
  assert.equal(ready.previewUrl, youtubePreview(job.id));
  assert.equal(applyYoutube(ready, { ...job, status: "failed", error: "Unavailable" }).previewUrl, undefined);
});

test("AI requests only a prepared session ID and numeric options", async () => {
  const original = globalThis.fetch;
  let body, endpoint;
  globalThis.fetch = async (url, options) => {
    endpoint = url; body = JSON.parse(options.body);
    return Response.json({ id: "run" }, { status: 202 });
  };
  try {
    const parameters = { imageSize: "640", confidence: "0.25", iou: "0.7", device: "cpu", classMode: "all", maxDet: "300", vidStride: "2", agnosticNms: false };
    await startRun(applyYoutube(source, job), "model", parameters, new AbortController().signal);
    assert.equal(endpoint, "/api/v1/runs/youtube");
    assert.equal(body.session_id, job.id);
    assert.equal(body.options.vid_stride, 2);
    assert.equal(body.url, undefined);
    await assert.rejects(startRun(source, "model", parameters, new AbortController().signal), /Chuẩn bị video/);
  } finally { globalThis.fetch = original; }
});

test("returning to YouTube restores active AI, while finished runs reset the preview", async () => {
  const signal = new AbortController().signal;
  const active = { id: "run", status: "running" };
  assert.equal(await restoreRun(async () => active, "youtube", signal), active);
  assert.equal(await restoreRun(async () => ({ status: "completed" }), "youtube", signal), null);
});
