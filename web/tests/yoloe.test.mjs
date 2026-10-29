import assert from "node:assert/strict";
import test from "node:test";
import { parseTextPrompts, validateTextPrompts, defaultTextPrompts } from "../src/features/pipelines/yolo/text-prompts.ts";
import { startRun } from "../src/features/inference/api.ts";

test("everyday defaults include people, vehicles and electronics; custom prompts keep class order", () => {
  assert.equal(validateTextPrompts(defaultTextPrompts), "");
  for (const prompt of ["person", "car", "motorcycle", "laptop", "computer monitor", "cell phone"])
    assert.ok(parseTextPrompts(defaultTextPrompts).includes(prompt));
  assert.deepEqual(parseTextPrompts(" laptop,\n person , cell phone, "), ["laptop", "person", "cell phone"]);
  for (const value of ["", "car, CAR", "x".repeat(81), "a\tb", Array.from({length:81}, (_, i) => `class${i}`).join(",")])
    assert.ok(validateTextPrompts(value), value);
});

test("all source routes transmit text prompts without stale model class filters", async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push(typeof init.body === "string" ? JSON.parse(init.body) : { options: JSON.parse(init.body.get("options")) });
    return Response.json({ id: "run" }, { status: 202 });
  };
  try {
    const parameters = { imageSize: "640", confidence: "0.25", iou: "0.7", device: "cpu", classMode: "selected", classes: ["999"], maxDet: "300", vidStride: "1", liveFps: "5", liveMinutes: "60", agnosticNms: false, textPromptEnabled: true, textPrompts: "laptop, person\ncell phone" };
    for (const kind of ["image", "screen", "video", "youtube", "stream", "webcam"]) {
      await startRun({ id: "source", kind, status: "ready", saved: true, youtubeSession: "session", deviceIndex: 0 }, "model", parameters, new AbortController().signal);
      assert.deepEqual(requests.at(-1).options.text_prompts, ["laptop", "person", "cell phone"]);
      assert.equal(requests.at(-1).options.classes, null);
    }
    await startRun({ id: "source", kind: "image", saved: true }, "yolo", { ...parameters, textPromptEnabled: false }, new AbortController().signal);
    assert.equal(requests.at(-1).options.text_prompts, undefined);
    assert.deepEqual(requests.at(-1).options.classes, [999]);
  } finally { globalThis.fetch = original; }
});
