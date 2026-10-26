import assert from "node:assert/strict";
import { test } from "node:test";
import {
  computeMediaTransform,
  projectPoint,
} from "../src/features/vision-overlay/geometry.ts";

const input = {
  viewportWidth: 640,
  viewportHeight: 640,
  mediaWidth: 1920,
  mediaHeight: 1080,
};
const near = (actual, expected) =>
  assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`);

test("contain aligns coordinates with image pixels, excluding letterbox", () => {
  const t = computeMediaTransform(input);
  assert.deepEqual(t, {
    x: 0,
    y: 140,
    width: 640,
    height: 360,
    clip: { x: 0, y: 140, width: 640, height: 360 },
  });
  assert.deepEqual(projectPoint(192, 108, { width: 1920, height: 1080 }, t), {
    x: 64,
    y: 176,
  });
  assert.deepEqual(
    projectPoint(0.1, 0.1, { width: 1920, height: 1080 }, t, true),
    { x: 64, y: 176 },
  );
});

test("cover crops and clips to media element instead of letterboxing", () => {
  const t = computeMediaTransform({ ...input, fit: "cover" });
  near(t.x, -248.8888888888889);
  near(t.y, 0);
  near(t.width, 1137.7777777777778);
  assert.deepEqual(t.clip, { x: 0, y: 0, width: 640, height: 640 });
  const center = projectPoint(960, 540, { width: 1920, height: 1080 }, t);
  near(center.x, 320);
  near(center.y, 320);
});

test("fill, offsets and off-center positioning use the correct CSS coordinate space", () => {
  const t = computeMediaTransform({ ...input, fit: "fill", x: 10, y: 20 });
  assert.deepEqual(projectPoint(1920, 1080, { width: 1920, height: 1080 }, t), {
    x: 650,
    y: 660,
  });
  const top = computeMediaTransform({ ...input, position: { x: 0, y: 0 } });
  assert.equal(top.y, 0);
  assert.deepEqual(top.clip, { x: 0, y: 0, width: 640, height: 360 });
});

test("mirrored coordinates and resized previews preserve frame geometry", () => {
  const t = computeMediaTransform({
    ...input,
    viewportWidth: 320,
    viewportHeight: 320,
  });
  const p = projectPoint(
    192,
    108,
    { width: 1920, height: 1080 },
    t,
    false,
    true,
  );
  near(p.x, 288);
  near(p.y, 88);
});

test("missing, hidden and invalid dimensions never produce NaN canvas coordinates", () => {
  for (const value of [0, -1, NaN, Infinity])
    assert.equal(computeMediaTransform({ ...input, mediaWidth: value }), null);
  const t = computeMediaTransform(input);
  assert.equal(projectPoint(NaN, 1, { width: 1920, height: 1080 }, t), null);
  assert.equal(projectPoint(1, 1, { width: 0, height: 1080 }, t), null);
});
