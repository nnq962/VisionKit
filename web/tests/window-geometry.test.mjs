import assert from "node:assert/strict";
import { test } from "node:test";
import { MIN_WINDOW_HEIGHT, MIN_WINDOW_WIDTH, resizeWindow } from "../src/features/logs/window-geometry.ts";

const initial = { x: 200, y: 180, width: 640, height: 470 };
const viewport = { width: 1280, height: 800 };

test("resizing east/south keeps the opposite corner fixed", () => {
  const next = resizeWindow(initial, "se", 120, 60, viewport);
  assert.deepEqual(next, { x: 200, y: 180, width: 760, height: 530 });
});

test("resizing north/west preserves the bottom-right corner", () => {
  const next = resizeWindow(initial, "nw", -100, -60, viewport);
  assert.equal(next.x, 100);
  assert.equal(next.y, 120);
  assert.equal(next.x + next.width, initial.x + initial.width);
  assert.equal(next.y + next.height, initial.y + initial.height);
});

test("shrinking cannot invert the rectangle or hide the controls", () => {
  for (const direction of ["n", "s", "e", "w", "ne", "nw", "se", "sw"]) {
    const next = resizeWindow(initial, direction, direction.includes("w") ? 10000 : -10000, direction.includes("n") ? 10000 : -10000, viewport);
    assert.ok(next.width >= MIN_WINDOW_WIDTH, direction);
    assert.ok(next.height >= MIN_WINDOW_HEIGHT, direction);
  }
});

test("all eight handles stop at the screen margin", () => {
  for (const direction of ["n", "s", "e", "w", "ne", "nw", "se", "sw"]) {
    const next = resizeWindow(initial, direction, direction.includes("w") ? -10000 : 10000, direction.includes("n") ? -10000 : 10000, viewport);
    assert.ok(next.x >= 12 && next.y >= 12, direction);
    assert.ok(next.x + next.width <= viewport.width - 12, direction);
    assert.ok(next.y + next.height <= viewport.height - 12, direction);
  }
});

test("a narrow or short screen takes priority over desktop minimum dimensions", () => {
  const small = { width: 325, height: 280 };
  const fitted = { x: 12, y: 12, width: 301, height: 256 };
  assert.deepEqual(resizeWindow(fitted, "se", -1000, -1000, small), fitted);
});
