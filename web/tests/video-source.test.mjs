import assert from "node:assert/strict";
import test from "node:test";
import { getSource, prepareVideo, saveSource } from "../src/features/sources/api.ts";
import { serializableDrafts } from "../src/features/sources/draft-storage.ts";

const record = {
  id: "video", name: "phone.MOV", kind: "video", location: "original.mov",
  metadata: { mime_type: "video/quicktime", codec: "hevc", format: "MOV" },
  content_url: "/api/v1/sources/video/content",
  preview_url: "/api/v1/sources/video/preview",
};

test("saved MOV uses browser playback while preserving original metadata and thumbnail", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async () => Response.json(record);
  try {
    const source = await getSource(record.id);
    assert.equal(source.previewUrl, "/api/v1/sources/video/playback");
    assert.equal(source.thumbnailUrl, record.preview_url);
    assert.equal(source.location, "original.mov");
    assert.equal(source.mimeType, "video/quicktime");
  } finally { globalThis.fetch = previous; }
});

test("draft preparation returns an MP4 File reused for saving and draft restoration", async () => {
  const previous = globalThis.fetch;
  const original = new File(["original HEVC"], "phone.MOV", { type: "video/quicktime" });
  const compatible = new Blob(["H264 preview"], { type: "video/mp4" });
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, body: options.body });
    return url.endsWith("/prepare-video") ? new Response(compatible) : Response.json(record);
  };
  try {
    const previewBlob = await prepareVideo(original);
    assert.equal(await previewBlob.text(), "H264 preview");
    const source = { id: "draft", kind: "video", status: "ready", file: previewBlob, previewBlob };
    await saveSource(source, "Camera");
    assert.equal(calls[0].url, "/api/v1/sources/prepare-video");
    assert.equal(calls[1].url, "/api/v1/sources/upload");
    assert.equal(await calls[1].body.get("file").text(), "H264 preview");
    assert.equal(calls[1].body.get("file").name, "phone.mp4");
    const snapshot = serializableDrafts("video", { video: { source, name: "Camera", save: false, location: "" } });
    assert.equal(snapshot.drafts.video.source.previewBlob, previewBlob);
    assert.equal(snapshot.drafts.video.source.file, previewBlob);
    assert.equal(previewBlob.type, "video/mp4");
    assert.equal(await original.text(), "original HEVC");
  } finally { globalThis.fetch = previous; }
});

test("preparation errors expose the backend error instead of returning invalid media", async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ detail: "Không đọc được video." }, { status: 415 });
  try {
    await assert.rejects(prepareVideo(new File(["invalid"], "broken.MOV")), /Không đọc được video/);
  } finally { globalThis.fetch = previous; }
});
