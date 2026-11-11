import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { captureSize, paintCapture, surfaceReady } from "../src/features/media-capture/capture-surface.ts";
import { captureFilename, PreviewRecorder, recordingMimeType } from "../src/features/media-capture/preview-recorder.ts";

let originals, frames, recorders, canvases;
class Element extends EventTarget {
  isConnected = true;
  paused = false;
  style = {};
  rect = { left: 10, top: 20, width: 640, height: 360 };
  getBoundingClientRect() { return this.rect; }
}
class Media extends Element { readyState = 2; videoWidth = 1920; videoHeight = 1080; }
class ImageMedia extends Element { complete = true; naturalWidth = 1920; naturalHeight = 1080; }
class Canvas extends Element {
  width = 640;
  height = 360;
  dataset = { captureReady: "true" };
  track = { stopped: false, stop() { this.stopped = true; } };
  calls = [];
  getContext() {
    return Object.fromEntries(["setTransform", "fillRect", "save", "restore", "scale", "translate", "drawImage"].map((method) => [method, (...args) => this.calls.push([method, ...args])]));
  }
  captureStream() { return { getTracks: () => [this.track] }; }
}
class Recorder {
  static supported = true;
  static supportedTypes = new Set(["video/webm;codecs=vp8"]);
  static fail = false;
  static isTypeSupported(type) { return this.supported && this.supportedTypes.has(type); }
  state = "inactive";
  constructor(stream, options) {
    if (Recorder.fail) throw Error("encoder failed");
    this.stream = stream;
    this.mimeType = options.mimeType;
    recorders.push(this);
  }
  start() { this.state = "recording"; }
  data(data) { this.ondataavailable({ data }); }
  stop() {
    this.state = "inactive";
    queueMicrotask(() => {
      this.data(new Blob(["final"]));
      this.onstop();
    });
  }
}

beforeEach(() => {
  frames = new Map(); recorders = []; canvases = [];
  Recorder.supported = true; Recorder.fail = false;
  Recorder.supportedTypes = new Set(["video/webm;codecs=vp8"]);
  const replacements = {
    HTMLVideoElement: Media, HTMLImageElement: ImageMedia, HTMLCanvasElement: Canvas,
    MediaRecorder: Recorder,
    document: { createElement() { const canvas = new Canvas(); canvases.push(canvas); return canvas; } },
    getComputedStyle: () => ({ objectFit: "contain", objectPosition: "50% 50%" }),
    requestAnimationFrame: (callback) => { const id = Math.random(); frames.set(id, callback); return id; },
    cancelAnimationFrame: (id) => frames.delete(id),
  };
  originals = Object.fromEntries(Object.keys(replacements).map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(replacements)) Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
});
afterEach(() => {
  for (const [key, descriptor] of Object.entries(originals)) {
    if (descriptor) Object.defineProperty(globalThis, key, descriptor);
    else delete globalThis[key];
  }
});

function fixture() {
  const states = [], saved = [], errors = [], notices = [];
  const media = new Media();
  let surface = { media, overlay: new Canvas() };
  const recorder = new PreviewRecorder({ state: (s) => states.push(s), saved: (b) => saved.push(b), error: (e) => errors.push(e), notice: (n) => notices.push(n) });
  return { recorder, media, states, saved, errors, notices, start: () => recorder.start(() => surface), replace: (s) => { surface = s; } };
}
function tick() {
  const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach((callback) => callback());
}

test("select a supported codec and report unavailable recording", () => {
  assert.equal(recordingMimeType(), "video/webm;codecs=vp8");
  Recorder.supported = false;
  assert.equal(recordingMimeType(), null);
  assert.throws(() => fixture().start(), /chưa hỗ trợ/);
});
test("prefer MP4 when MP4 and WebM are both supported and preserve the output type", async () => {
  Recorder.supportedTypes.add("video/mp4");
  assert.equal(recordingMimeType(), "video/mp4");
  const f = fixture(); f.start();
  assert.equal(recorders[0].mimeType, "video/mp4");
  await f.recorder.stop();
  assert.equal(f.saved[0].type, "video/mp4");
});
test("prefer H.264 for MP4 when the browser supports it", async () => {
  Recorder.supportedTypes.add("video/mp4");
  Recorder.supportedTypes.add("video/mp4;codecs=avc1");
  assert.equal(recordingMimeType(), "video/mp4;codecs=avc1");
  const f = fixture(); f.start();
  await f.recorder.stop();
  assert.equal(f.saved[0].type, "video/mp4;codecs=avc1");
});
test("fall back to a supported WebM codec when MP4 is unavailable", async () => {
  Recorder.supportedTypes = new Set(["video/webm", "video/webm;codecs=vp8", "video/webm;codecs=vp9"]);
  assert.equal(recordingMimeType(), "video/webm;codecs=vp9");
  const f = fixture(); f.start();
  await f.recorder.stop();
  assert.equal(f.saved[0].type, "video/webm;codecs=vp9");
});
test("stop saves all chunks including the final chunk without stopping or pausing the source", async () => {
  const f = fixture(); f.start();
  recorders[0].data(new Blob(["first"]));
  const first = f.recorder.stop(), second = f.recorder.stop();
  assert.equal(first, second);
  await first;
  assert.deepEqual(f.states, ["recording", "stopping", "idle"]);
  assert.equal(await f.saved[0].text(), "firstfinal");
  assert.equal(f.saved[0].type, "video/webm;codecs=vp8");
  assert.equal(f.media.paused, false);
  assert.equal(canvases[0].track.stopped, true);
  assert.equal(frames.size, 0);
  f.media.dispatchEvent(new Event("ended"));
  assert.equal(f.saved.length, 1);
});
test("repeated start/stop creates independent clips and does not duplicate starts", async () => {
  const f = fixture(); f.start(); f.start();
  assert.equal(recorders.length, 1);
  await f.recorder.stop(); f.start();
  recorders[1].data(new Blob(["second"]));
  await f.recorder.stop();
  assert.equal(f.saved.length, 2);
  assert.equal(await f.saved[1].text(), "secondfinal");
});
test("end of playback and removal/replacement of the preview finalize the clip", async () => {
  for (const reason of ["ended", "emptied", "error", "removed", "replaced"]) {
    const f = fixture(); f.start();
    if (reason === "removed") { f.media.isConnected = false; tick(); }
    else if (reason === "replaced") { f.replace({ media: new Media() }); tick(); }
    else f.media.dispatchEvent(new Event(reason));
    await f.recorder.stop();
    assert.equal(f.saved.length, 1, reason);
    assert.equal(frames.size, 0, reason);
  }
});
test("encoder startup and cross-origin capture failures release resources", () => {
  const f = fixture(); Recorder.fail = true;
  assert.throws(() => f.start(), /encoder failed/);
  assert.equal(canvases[0].track.stopped, true);
  assert.equal(frames.size, 0);
  Recorder.fail = false; f.media.readyState = 0;
  assert.throws(() => f.start(), /Chưa có hình ảnh/);
  f.media.readyState = 2;
  const captureStream = Canvas.prototype.captureStream;
  try {
    Canvas.prototype.captureStream = () => { throw new DOMException("Tainted canvas", "SecurityError"); };
    assert.throws(() => f.start(), { name: "SecurityError" });
    assert.equal(frames.size, 0);
  } finally { Canvas.prototype.captureStream = captureStream; }
});
test("encoding errors and frame failures preserve the recorded portion", async () => {
  for (const failure of ["encoder", "frame"]) {
    const f = fixture(); f.start(); recorders.at(-1).data(new Blob(["valid"]));
    if (failure === "encoder") recorders.at(-1).onerror();
    else { f.media.readyState = 0; tick(); }
    await f.recorder.stop();
    assert.equal(await f.saved[0].text(), "validfinal");
    assert.equal(f.errors.length, 1);
    assert.equal(frames.size, 0);
  }
});
test("large recordings automatically finalize at the memory limit", async () => {
  const f = fixture(); f.start();
  const data = new Blob(["large"]);
  Object.defineProperty(data, "size", { value: 256 * 1024 * 1024 });
  recorders[0].data(data);
  await f.recorder.stop();
  assert.equal(f.saved.length, 1);
  assert.match(f.notices[0], /256 MB/);
});
test("capture preserves letterboxing and overlays in the same coordinate system", () => {
  const media = new Media(); media.videoWidth = 640; media.videoHeight = 480;
  const overlay = new Canvas(), output = new Canvas();
  overlay.rect = media.rect;
  paintCapture(output, { media, overlay });
  const draws = output.calls.filter(([method]) => method === "drawImage");
  assert.deepEqual(draws[0].slice(2), [80, 0, 480, 360]);
  assert.deepEqual(draws[1].slice(2), [0, 0, 640, 360]);
  media.style.transform = "scaleX(-1)";
  paintCapture(output, { media, overlay });
  assert.ok(output.calls.some(([method, x, y]) => method === "scale" && x === -1 && y === 1));
});
test("capture resolution is even, bounded, stable and readiness excludes blank media", () => {
  const media = new Media(); assert.deepEqual(captureSize({ media }), { width: 1920, height: 1080 });
  media.videoWidth = 7680; media.videoHeight = 4320;
  assert.deepEqual(captureSize({ media }), { width: 1920, height: 1080 });
  media.readyState = 1; assert.equal(surfaceReady({ media }), false);
  const image = new ImageMedia(); assert.equal(surfaceReady({ media: image }), true);
  image.naturalWidth = 0; assert.equal(surfaceReady({ media: image }), false);
  const canvas = new Canvas(); canvas.dataset.captureReady = "false";
  assert.equal(surfaceReady({ media: canvas }), false);
  canvas.dataset.captureReady = "true"; assert.equal(surfaceReady({ media: canvas }), true);
  assert.match(captureFilename("camera/test.mp4", "webm"), /^visionkit-camera-test-.*\.webm$/);
});
