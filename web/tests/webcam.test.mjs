import test from "node:test";
import assert from "node:assert/strict";
import { startRun } from "../src/features/inference/api.ts";

test("local webcam run sends an integer device index, never browser media", async () => {
  const original = globalThis.fetch;
  let endpoint, body;
  globalThis.fetch = async (url, options) => { endpoint = url; body = JSON.parse(options.body); return Response.json({ id: "run" }); };
  try {
    const source = { id: "camera", kind: "webcam", deviceIndex: 0, status: "ready", location: "0" };
    const parameters = { imageSize: "640", confidence: "0.25", iou: "0.7", device: "auto", classMode: "all", maxDet: "300", vidStride: "1", liveFps: "5", liveMinutes: "60" };
    await startRun(source, "yolo", parameters, new AbortController().signal);
    assert.equal(endpoint, "/api/v1/runs/webcam");
    assert.equal(body.device_index, 0);
    assert.equal(body.duration_seconds, 3600);
    assert.equal(body.options.max_fps, 5);
    assert.equal(body.stream_url, undefined);
    assert.equal(body.mediaStream, undefined);
    await assert.rejects(startRun({ ...source, status: "pending" }, "yolo", parameters, new AbortController().signal), /Kiểm tra webcam/);
  } finally { globalThis.fetch = original; }
});


test("webcam reload retains configured device but never stores camera images", async () => {
  const { serializableDrafts } = await import("../src/features/sources/draft-storage.ts");
  const draft = { source: { id: "webcam", kind: "webcam", deviceIndex: 0, status: "ready", previewUrl: "data:image/jpeg;base64,private-frame" }, location: "0", name: "Webcam 0", save: false };
  const restored = serializableDrafts("webcam", { webcam: draft }).drafts.webcam.source;
  assert.equal(restored.status, "ready");
  assert.equal(restored.deviceIndex, 0);
  assert.equal(restored.previewUrl, undefined);
  assert.equal(JSON.stringify(restored).includes("private-frame"), false);
});
