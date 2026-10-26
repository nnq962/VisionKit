import assert from "node:assert/strict";
import { test } from "node:test";
import { restoreRun } from "../src/features/inference/restore-run.ts";

const lastFrame = { frameId: 980, timestampMs: 40833, detections: [{ bbox: [1, 2, 30, 40] }] };

test("returning from step 3 does not hydrate a finished video's last frame or progress", async () => {
  const savedRun = { id: "completed-video", status: "completed", result: lastFrame, progress: { percent: 100 } };
  const restored = await restoreRun(async () => savedRun, "video", new AbortController().signal);
  assert.equal(restored, null);
  assert.equal(savedRun.result.timestampMs, 40833); // Không sửa/xoá kết quả lượt cũ.
});

test("leaving and returning during inference still recovers the active video run", async () => {
  for (const status of ["queued", "running"]) {
    const savedRun = { id: "active-video", status, result: status === "running" ? lastFrame : null };
    assert.equal(await restoreRun(async () => savedRun, "video", new AbortController().signal), savedRun);
  }
});

test("cancelled/failed videos reset their preview while completed image results remain restorable", async () => {
  for (const status of ["completed", "cancelled", "failed"]) {
    const savedRun = { id: "previous-run", status, result: lastFrame };
    assert.equal(await restoreRun(async () => savedRun, "video", new AbortController().signal), null);
    assert.equal(await restoreRun(async () => savedRun, "image", new AbortController().signal), savedRun);
  }
});

test("a late restore response is discarded after leaving the step or starting a new run", async () => {
  let resolve;
  const controller = new AbortController();
  const restored = restoreRun(() => new Promise((done) => { resolve = done; }), "video", controller.signal);
  controller.abort();
  resolve({ id: "old-active-run", status: "running", result: lastFrame });
  assert.equal(await restored, null);
});
