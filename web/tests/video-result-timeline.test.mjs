import assert from "node:assert/strict";
import test from "node:test";
import { VideoResultTimeline } from "../src/features/inference/video-result-timeline.ts";

const frame = (timestampMs, detections = ["box"]) => ({ timestampMs, detections });

test("early AI results wait for the video's clock, without showing future boxes", () => {
  const queue = new VideoResultTimeline();
  const first = frame(1000), second = frame(1100);
  queue.push(first, 0);
  queue.push(second, 0);
  assert.equal(queue.at(999), null);
  assert.equal(queue.at(1000), first);
  assert.equal(queue.at(1099), first);
  assert.equal(queue.at(1100), second);
});

test("late AI results are dropped and previous boxes expire while video continues", () => {
  const queue = new VideoResultTimeline();
  const current = frame(1000);
  queue.push(current, 1000);
  assert.equal(queue.at(1000), current);
  queue.push(frame(500), 1200);
  assert.equal(queue.at(1200), null);
  assert.equal(queue.at(5000), null);
});

test("empty detections clear old boxes exactly when their frame is due", () => {
  const queue = new VideoResultTimeline();
  const present = frame(0), empty = frame(100, []);
  queue.push(present, 0);
  queue.push(empty, 0);
  assert.equal(queue.at(0), present);
  assert.equal(queue.at(99), present);
  assert.equal(queue.at(100), empty);
});

test("duplicate and out-of-order WS/poll results cannot rewind the overlay", () => {
  const queue = new VideoResultTimeline();
  const first = frame(100), second = frame(200), replacement = frame(200, []);
  queue.push(second, 0);
  queue.push(first, 0);
  queue.push(replacement, 0);
  assert.equal(queue.at(100), first);
  assert.equal(queue.at(200), replacement);
  queue.push(first, 200);
  assert.equal(queue.at(210), replacement);
});

test("missing or invalid timestamps cannot paint boxes on an unrelated frame", () => {
  const queue = new VideoResultTimeline();
  for (const time of [undefined, NaN, Infinity, -1]) queue.push(frame(time), 0);
  assert.equal(queue.at(0), null);
});

test("buffering uses media time rather than wall time and retains nearest future frames", () => {
  const queue = new VideoResultTimeline(150, 3);
  const first = frame(100), second = frame(200), third = frame(300);
  for (const item of [third, frame(400), second, first]) queue.push(item, 0);
  assert.equal(queue.at(100), first);
  assert.equal(queue.at(100), first);
  assert.equal(queue.at(200), second);
  assert.equal(queue.at(300), third);
  assert.equal(queue.at(500), null);
});

test("AI can complete early: queued boxes still play out against video time", () => {
  const queue = new VideoResultTimeline();
  const results = Array.from({ length: 10 }, (_, i) => frame(i * 100));
  for (const item of results) queue.push(item, 0);
  for (let time = 0; time < 1000; time += 17) {
    const selected = queue.at(time);
    assert.ok(selected.timestampMs <= time);
    assert.ok(time - selected.timestampMs <= 150);
  }
});
