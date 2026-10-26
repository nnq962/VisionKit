import assert from "node:assert/strict";
import { test } from "node:test";
import { inspectRtspUrl } from "../src/features/sources/rtsp-configuration.ts";

test("RTSP URL summary includes endpoint without exposing credentials, path or query", () => {
  const parsed = inspectRtspUrl("rtsp://user:private-secret@192.168.1.10:8554/private/path?token=private-token");
  assert.equal(parsed.error, "");
  assert.deepEqual(parsed.endpoint, { protocol: "RTSP", host: "192.168.1.10", port: "8554", authenticated: true });
  for (const secret of ["user", "private-secret", "private/path", "private-token"]) assert.ok(!JSON.stringify(parsed).includes(secret));
});

test("default ports, IPv6 and secure URLs produce useful connection summaries", () => {
  assert.equal(inspectRtspUrl(" rtsp://camera/live ").endpoint.port, "554");
  assert.equal(inspectRtspUrl("rtsps://camera/live").endpoint.port, "322");
  assert.equal(inspectRtspUrl("rtsp://[::1]:8554/live").endpoint.host, "[::1]");
});

test("invalid protocols, malformed ports, whitespace, empty input and fragments fail without echoing input", () => {
  for (const url of ["", "http://secret-host/live", "rtsp:///", "rtsp://host:0/live", "rtsp://host:65536/live", "rtsp://host:abc/live", "rtsp://host/live\nsecret", "rtsp://host/live#secret"]) {
    const result = inspectRtspUrl(url);
    assert.ok(result.error, url);
    assert.equal(result.endpoint, null);
    assert.ok(!result.error.includes("secret"));
  }
});
