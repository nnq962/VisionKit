import assert from 'node:assert/strict';
import { test } from 'node:test';
import { releaseTemporaryModel } from '../src/features/models/api.ts';
import { finishRun } from '../src/features/inference/api.ts';

test('cleanup retries tolerate an already removed temporary model but surface in-use errors', async () => {
  const original = globalThis.fetch;
  try {
    for (const status of [204, 404, 410]) {
      globalThis.fetch = async () => new Response(null, { status });
      await releaseTemporaryModel('temporary-model');
    }
    globalThis.fetch = async () => Response.json({ detail: 'Model đang dùng' }, { status: 409 });
    await assert.rejects(releaseTemporaryModel('temporary-model'), /Model đang dùng/);
  } finally { globalThis.fetch = original; }
});

test('completion uses the resource cleanup endpoint and reports failure for UI retry', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/v1/runs/run-id/resources');
      assert.equal(options.method, 'DELETE');
      return new Response(null, { status: 204 });
    };
    await finishRun('run-id');
    globalThis.fetch = async () => new Response(null, { status: 503 });
    await assert.rejects(finishRun('run-id'), /Chưa dọn được/);
  } finally { globalThis.fetch = original; }
});
