import assert from "node:assert/strict";
import test from "node:test";
import {
  regionTotals,
  validateMonitorSettings,
} from "../src/features/zone-counting/monitoring.ts";
import {
  regionPoint,
  polygonError,
} from "../src/features/zone-counting/geometry.ts";
import { computeMediaTransform } from "../src/features/vision-overlay/geometry.ts";
import { medicalClasses } from "../src/features/zone-counting/types.ts";
import {
  saveCountingProfile,
  startCountingProfile,
  stopCountingProfile,
  duplicateCountingProfile,
  deleteCountingProfile,
  restoreCountingProfile,
  saveCountingConfig,
  startCountingRun,
} from "../src/features/zone-counting/api.ts";

test("drawing in a letterboxed portrait video maps to original normalized image coordinates", () => {
  const transform = computeMediaTransform({
    viewportWidth: 800,
    viewportHeight: 450,
    mediaWidth: 1080,
    mediaHeight: 1920,
  });
  assert.equal(regionPoint(0, 100, transform), null);
  assert.deepEqual(regionPoint(400, 225, transform), [0.5, 0.5]);
  assert.deepEqual(regionPoint(-50, 600, transform, true), [0, 1]);
  const resized = computeMediaTransform({
    viewportWidth: 400,
    viewportHeight: 225,
    mediaWidth: 1080,
    mediaHeight: 1920,
  });
  assert.deepEqual(regionPoint(200, 112.5, resized), [0.5, 0.5]);
  assert.equal(regionPoint(0, 0, { ...transform, width: 0, height: 0 }), null);
});

test("polygon editor accepts concave regions and rejects invalid shapes before persistence", () => {
  assert.equal(
    polygonError([
      [0, 0],
      [1, 0],
      [1, 0.4],
      [0.4, 0.4],
      [0.4, 1],
      [0, 1],
    ]),
    "",
  );
  for (const points of [
    [],
    [
      [0, 0],
      [1, 1],
    ],
    [
      [0, 0],
      [1, 1],
      [0, 1],
      [1, 0],
    ],
    [
      [0, 0],
      [0.5, 0],
      [1, 0],
    ],
    [
      [0, 0],
      [1, 0],
      [0, 0],
    ],
    [
      [0, 0],
      [1, 0],
      [0.5, 0],
      [1, 1],
      [0, 1],
    ],
    [
      [0, 0],
      [-0.1, 0.5],
      [1, 1],
    ],
    [
      [0, 0],
      [NaN, 0],
      [1, 1],
    ],
  ])
    assert.ok(polygonError(points));
});

test("configuration and count-run APIs keep the source signature and full normalized polygon", async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, ...init, body: JSON.parse(init.body) });
    return Response.json({ id: "run" });
  };
  const config = {
    version: 1,
    classes: ["person", "laptop", "cell phone"],
    reference_width: 1920,
    reference_height: 1080,
    zones: [
      {
        id: "zone",
        name: "A",
        color: "#22d3ee",
        classes: ["person"],
        points: [
          [0, 0],
          [1, 0],
          [1, 1],
          [0, 1],
        ],
      },
    ],
  };
  try {
    await saveCountingConfig("source-id", "signature", config);
    assert.equal(requests[0].url, "/api/v1/counting/sources/source-id");
    assert.deepEqual(requests[0].body, {
      source_signature: "signature",
      config,
    });
    await startCountingRun(
      "source-id",
      "model-id",
      "signature",
      config,
      { conf: 0.25, iou: 0.7, device: "auto", max_fps: 5 },
      60,
    );
    assert.equal(requests[1].url, "/api/v1/counting/runs");
    assert.equal(requests[1].body.duration_seconds, 3600);
    assert.deepEqual(requests[1].body.config, config);
    assert.equal(requests[1].body.source_id, "source-id");
    assert.equal(requests[1].body.stream_url, undefined);
    assert.deepEqual(
      medicalClasses.map(([key]) => key),
      [
        "person",
        "wheelchair",
        "hospital stretcher",
        "hospital bed",
        "medical trolley",
        "IV pole",
      ],
    );
    globalThis.fetch = async () =>
      Response.json({ detail: "Nguồn đã thay đổi" }, { status: 409 });
    await assert.rejects(
      startCountingRun("s", "m", "sig", config, {}, 60),
      /Nguồn đã thay đổi/,
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("monitor totals distinguish missing data from zero and honor the selected regions", () => {
  const counts = {
    valid: true,
    regions: [
      { id: "a", counts: { person: 2, laptop: 0 } },
      { id: "b", counts: { person: 3 } },
    ],
  };
  assert.deepEqual(
    regionTotals(counts, ["person", "laptop", "dog"], ["a", "b"]),
    [5, 0, null],
  );
  assert.deepEqual(regionTotals(counts, ["person"], ["b"]), [3]);
  assert.deepEqual(regionTotals(null, ["person"], ["a"]), [null]);
  assert.deepEqual(
    regionTotals({ ...counts, valid: false }, ["person"], ["a"]),
    [null],
  );
  assert.deepEqual(regionTotals(counts, ["person"], ["missing"]), [null]);
  assert.deepEqual(regionTotals(counts, ["person"], []), [null]);
});

test("monitor settings reject invalid thresholds and duration before saving", () => {
  const settings = {
    model_id: "yoloe.pt",
    options: { conf: 0.25, iou: 0.7, max_fps: 5, device: "auto" },
    duration_seconds: 3600,
  };
  assert.equal(validateMonitorSettings(settings), "");
  for (const patch of [
    { model_id: "" },
    { continuous: false, auto_start: true },
    { duration_seconds: 61 },
    { duration_seconds: 0 },
    { duration_seconds: 14460 },
    { options: { ...settings.options, conf: NaN } },
    { options: { ...settings.options, iou: 1.1 } },
    { options: { ...settings.options, max_fps: 0 } },
  ])
    assert.ok(validateMonitorSettings({ ...settings, ...patch }));
});

test("saving monitor settings uses the same atomic configuration request", async () => {
  const original = globalThis.fetch;
  let body;
  globalThis.fetch = async (_url, init) => {
    body = JSON.parse(init.body);
    return Response.json({ config: body.config, monitor: body.monitor });
  };
  try {
    const config = {
      version: 1,
      classes: ["person"],
      reference_width: 100,
      reference_height: 100,
      zones: [],
    };
    const monitor = {
      model_id: "yoloe.pt",
      options: { conf: 0.3, iou: 0.7, max_fps: 5, device: "auto" },
      duration_seconds: 3600,
    };
    const saved = await saveCountingConfig(
      "source",
      "signature",
      config,
      monitor,
    );
    assert.deepEqual(body, { source_signature: "signature", config, monitor });
    assert.deepEqual(saved.monitor, monitor);
  } finally {
    globalThis.fetch = original;
  }
});

test("named profiles create separately, update by id and run the server snapshot", async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, ...init });
    return Response.json({ id: "profile-id" });
  };
  try {
    const body = {
      name: "Cấu hình 1",
      source_id: "video",
      source_signature: "sig",
      config: { zones: [] },
      monitor: { model_id: "yoloe.pt" },
    };
    await saveCountingProfile(null, body);
    await saveCountingProfile("profile-id", { ...body, name: "Cấu hình 2" });
    await startCountingProfile("profile-id");
    assert.equal(requests[0].url, "/api/v1/counting/profiles");
    assert.equal(requests[0].method, "POST");
    assert.deepEqual(JSON.parse(requests[0].body), body);
    assert.equal(requests[1].url, "/api/v1/counting/profiles/profile-id");
    assert.equal(requests[1].method, "PUT");
    assert.equal(requests[2].url, "/api/v1/counting/profiles/profile-id/runs");
    assert.equal(requests[2].method, "POST");
    assert.equal(requests[2].body, undefined);
  } finally {
    globalThis.fetch = original;
  }
});

test("profile management and stopping call dedicated durable service endpoints", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push([url, init.method]);
    return Response.json({ id: "id", enabled: false });
  };
  try {
    await stopCountingProfile("id");
    await duplicateCountingProfile("id");
    await deleteCountingProfile("id");
    await restoreCountingProfile("id");
    assert.deepEqual(calls, [
      ["/api/v1/counting/profiles/id/stop", "POST"],
      ["/api/v1/counting/profiles/id/duplicate", "POST"],
      ["/api/v1/counting/profiles/id", "DELETE"],
      ["/api/v1/counting/profiles/id/restore", "POST"],
    ]);
  } finally {
    globalThis.fetch = original;
  }
});
