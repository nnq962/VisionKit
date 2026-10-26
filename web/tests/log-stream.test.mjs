import assert from "node:assert/strict";
import { test } from "node:test";
import { INITIAL_LOG_STATE, LogStream, MAX_LOG_ENTRIES, mergeLogPage, parseLogPage } from "../src/features/logs/log-stream.ts";

const epoch = "a".repeat(32);
const cursor = (id) => `${epoch}:${id}`;
const entry = (id) => ({ id: cursor(id), timestamp: "2026-10-26T03:00:00Z", service: "ai", level: "ERROR", logger: "app.worker", message: `entry ${id}`, run_id: null, traceback: "RuntimeError: example", source_id: null });
const page = (items = [], overrides = {}) => ({ items, next_cursor: items.at(-1)?.id ?? cursor(0), has_more: false, reset: false, dropped: false, ai: { configured: true, available: true, last_success_at: null, reset_count: 0, dropped_batches: 0 }, ...overrides });
const response = (body) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
const flush = () => new Promise((resolve) => setImmediate(resolve));
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("bounds memory, deduplicates overlapping pages, preserves traceback", () => {
  let state = INITIAL_LOG_STATE;
  for (let start = 1; start <= 2500; start += 250) {
    state = mergeLogPage(state, page(Array.from({ length: 250 }, (_, index) => entry(start + index))));
  }
  state = mergeLogPage(state, page([entry(2500), entry(2500)]));
  assert.equal(state.entries.length, MAX_LOG_ENTRIES);
  assert.equal(state.entries[0].id, cursor(501));
  assert.equal(state.entries.at(-1).traceback, "RuntimeError: example");
});

test("restart replaces previous history; backend and AI gaps remain explicit", () => {
  let state = mergeLogPage(INITIAL_LOG_STATE, page([entry(1)]));
  state = mergeLogPage(state, page([], { dropped: true }));
  assert.match(state.notice, /hết hạn/);
  state = mergeLogPage(state, page([entry(2)], { reset: true }));
  assert.deepEqual(state.entries.map((item) => item.id), [cursor(2)]);
  assert.match(state.notice, /khởi động lại/);
  state = mergeLogPage(state, page([], { ai: { ...state.ai, reset_count: 1 } }));
  assert.match(state.notice, /AI bị gián đoạn/);
});

test("rejects malformed pages without consuming their cursor", () => {
  assert.equal(parseLogPage(page()).items.length, 0);
  for (const invalid of [null, {}, page([], { next_cursor: "bad" }), page([{}]), page([entry(1)], { ai: null }), page([{ ...entry(1), timestamp: "bad" }])]) {
    assert.throws(() => parseLogPage(invalid));
  }
});

test("empty pages advance cursor; clear and pause/resume do not replay history", async () => {
  const urls = [];
  const reader = new LogStream(() => {}, async (url) => {
    urls.push(url);
    return response(page(urls.length === 1 ? [entry(1)] : [], { next_cursor: cursor(urls.length) }));
  });
  try {
    reader.start(); await flush(); reader.stop();
    assert.equal(reader.state.entries.length, 1);
    reader.clear();
    reader.start(); await flush(); reader.stop();
    reader.start(); await flush(); reader.stop();
    assert.equal(reader.state.entries.length, 0);
    assert.equal(new URL(urls[1], "http://local").searchParams.get("after"), cursor(1));
    assert.equal(new URL(urls[2], "http://local").searchParams.get("after"), cursor(2));
  } finally { reader.stop(); }
});

test("stop aborts pending request and ignores late response from previous generation", async () => {
  let resolveOld;
  let oldSignal;
  let calls = 0;
  const reader = new LogStream(() => {}, async (_, options) => {
    calls++;
    if (calls === 1) {
      oldSignal = options.signal;
      return new Promise((resolve) => { resolveOld = resolve; });
    }
    return response(page([entry(2)]));
  });
  try {
    reader.start(); reader.stop();
    assert.equal(oldSignal.aborted, true);
    reader.start(); await flush();
    resolveOld(response(page([entry(1)]))); await flush();
    assert.deepEqual(reader.state.entries.map((item) => item.id), [cursor(2)]);
  } finally { reader.stop(); }
});

test("drains has_more sequentially without overlapping requests", async () => {
  let calls = 0;
  let inFlight = 0;
  let maximum = 0;
  const reader = new LogStream(() => {}, async () => {
    maximum = Math.max(maximum, ++inFlight);
    const id = ++calls;
    await wait(2);
    inFlight--;
    return response(page([entry(id)], { has_more: id < 3 }));
  });
  try {
    reader.start();
    for (let i = 0; i < 30 && reader.state.entries.length < 3; i++) await wait(5);
    assert.equal(calls, 3);
    assert.equal(maximum, 1);
    assert.equal(reader.state.entries.length, 3);
    reader.stop(); await wait(20);
    assert.equal(calls, 3);
  } finally { reader.stop(); }
});

test("automatically retries errors with retained entries and cursor", async () => {
  const urls = [];
  const reader = new LogStream(() => {}, async (url) => {
    urls.push(url);
    if (urls.length === 2) throw new Error("offline");
    return response(page([entry(urls.length)]));
  });
  try {
    reader.start(); await flush(); reader.stop();
    reader.start(); await flush();
    assert.equal(reader.state.connection, "offline");
    assert.equal(reader.state.entries.length, 1);
    for (let i = 0; i < 30 && urls.length < 3; i++) await wait(50);
    assert.equal(reader.state.connection, "online");
    assert.equal(new URL(urls[2], "http://local").searchParams.get("after"), cursor(1));
    assert.equal(reader.state.entries.length, 2);
  } finally { reader.stop(); }
});


test("AI outage is separate from backend availability and notices can be dismissed", async () => {
  const reader = new LogStream(() => {}, async () => response(page([entry(1)], {
    dropped: true, ai: { configured: true, available: false, last_success_at: null, reset_count: 0, dropped_batches: 0 },
  })));
  try {
    reader.start(); await flush(); reader.stop();
    assert.equal(reader.state.connection, "online");
    assert.equal(reader.state.ai.available, false);
    assert.ok(reader.state.notice);
    reader.dismissNotice();
    assert.equal(reader.state.notice, null);
    assert.equal(reader.state.entries.length, 1);
  } finally { reader.stop(); }
});
