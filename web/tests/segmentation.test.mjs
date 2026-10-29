import assert from "node:assert/strict";
import test from "node:test";
import { drawDetections } from "../src/features/vision-overlay/draw.ts";
import { computeMediaTransform } from "../src/features/vision-overlay/geometry.ts";

function context() {
  const calls = [];
  const ctx = { calls, globalAlpha: 1, measureText: () => ({ width: 20 }) };
  for (const method of ["save", "restore", "beginPath", "rect", "clip", "moveTo", "lineTo", "closePath", "fill", "stroke", "strokeRect", "fillRect", "fillText", "arc"])
    ctx[method] = (...args) => calls.push([method, ...args]);
  return ctx;
}
const transform = computeMediaTransform({ viewportWidth: 200, viewportHeight: 200, mediaWidth: 100, mediaHeight: 50 });
const detection = { classId: 0, confidence: 0.9, bbox: [10, 10, 30, 30], polygon: [[10, 10], [30, 10], [30, 30]] };
const frame = { sourceSize: { width: 100, height: 50 }, detections: [detection] };

test("segmentation projects through letterbox, clips to video and works with boxes disabled", () => {
  const ctx = context();
  drawDetections(ctx, frame, transform, { showSegments: true, showBoxes: false, showLabels: false });
  assert.ok(ctx.calls.some(([name]) => name === "fill"));
  assert.ok(ctx.calls.some(([name]) => name === "closePath"));
  assert.deepEqual(ctx.calls.find(([name]) => name === "moveTo"), ["moveTo", 20, 70]);
  assert.deepEqual(ctx.calls.find(([name]) => name === "rect"), ["rect", 0, 50, 200, 100]);
  assert.ok(!ctx.calls.some(([name]) => name === "strokeRect"));
});

test("mask toggle leaves bbox rendering available; masks are behind every bbox", () => {
  for (const showSegments of [false, undefined]) {
    const ctx = context();
    drawDetections(ctx, frame, transform, { showSegments, showLabels: false });
    assert.ok(!ctx.calls.some(([name]) => name === "fill"));
    assert.ok(ctx.calls.some(([name]) => name === "strokeRect"));
  }
  const ctx = context();
  drawDetections(ctx, { ...frame, detections: [detection, detection] }, transform, { showSegments: true, showLabels: false });
  assert.ok(ctx.calls.findLastIndex(([name]) => name === "fill") < ctx.calls.findIndex(([name]) => name === "strokeRect"));
});

test("invalid or low-confidence polygons do not draw; normalized and mirrored masks align", () => {
  for (const polygon of [undefined, [], [[1, 2]], [[0, 0], [NaN, 2], [4, 5]], [[0, 0], null, [4, 5]]]) {
    const ctx = context();
    drawDetections(ctx, { ...frame, detections: [{ ...detection, polygon }] }, transform, { showSegments: true });
    assert.ok(!ctx.calls.some(([name]) => name === "fill"));
  }
  const filtered = context();
  drawDetections(filtered, frame, transform, { showSegments: true, confidenceThreshold: 0.95 });
  assert.ok(!filtered.calls.some(([name]) => name === "fill"));
  const ctx = context();
  drawDetections(ctx, { ...frame, coordinates: "normalized", detections: [{ polygon: [[0.1, 0.2], [0.3, 0.2], [0.3, 0.6]] }] }, transform, { showSegments: true, mirrored: true });
  assert.deepEqual(ctx.calls.find(([name]) => name === "moveTo"), ["moveTo", 180, 70]);
});
