import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./index.js";

const env = { GITHUB_TOKEN: "test-token", TRIGGER_SECRET: "test-secret" };
const origin = "https://status.chi.qzz.io";

function request(body, { method = "POST", key = "test-secret", requestOrigin = origin, url = "https://worker.example/" } = {}) {
  const headers = new Headers({ Origin: requestOrigin });
  if (key !== null) headers.set("X-Trigger-Key", key);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  return new Request(url, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

async function jsonResponse(response) {
  return { status: response.status, body: await response.json() };
}

test("rejects requests with an unapproved Origin", async () => {
  const response = await worker.fetch(request({}, { requestOrigin: "https://evil.example" }), env);
  assert.equal(response.status, 403);
});

test("rejects a missing or incorrect trigger key", async () => {
  const missing = await worker.fetch(request({}, { key: null }), env);
  const incorrect = await worker.fetch(request({}, { key: "wrong" }), env);
  assert.equal(missing.status, 401);
  assert.equal(incorrect.status, 401);
});

test("rejects dispatch to a workflow outside the allowlist", async () => {
  const response = await worker.fetch(request({ repository: "attacker/repo", workflow: "deploy.yml" }), env);
  assert.equal(response.status, 403);
});

test("rejects non-main refs and unsupported inputs", async () => {
  const wrongRef = await worker.fetch(request({ ref: "feature" }), env);
  const wrongInput = await worker.fetch(request({ repository: "tsai97216/status", workflow: "update-status.yml", inputs: { arbitrary: "value" } }), env);
  assert.equal(wrongRef.status, 400);
  assert.equal(wrongInput.status, 400);
});

test("dispatches an approved workflow with only validated inputs", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url: String(url), options };
    return new Response(null, { status: 204 });
  };
  try {
    const response = await worker.fetch(request({
      repository: "tsai97216/chi-source",
      workflow: "main.yml",
      ref: "main",
      inputs: { app: "all" },
    }), env);
    const result = await jsonResponse(response);
    assert.equal(response.status, 202);
    assert.equal(result.body.ok, true);
    assert.match(captured.url, /tsai97216\/chi-source\/actions\/workflows\/main\.yml\/dispatches$/);
    assert.equal(captured.options.headers.Authorization, "Bearer test-token");
    assert.deepEqual(JSON.parse(captured.options.body), { ref: "main", inputs: { app: "all" } });
    assert.ok(captured.options.signal instanceof AbortSignal);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("returns a generic gateway error when GitHub API cannot be reached", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError("simulated network failure"); };
  try {
    const response = await worker.fetch(request({}), env);
    const result = await jsonResponse(response);
    assert.equal(response.status, 502);
    assert.equal(result.body.ok, false);
    assert.match(result.body.error, /Could not reach/);
    assert.doesNotMatch(JSON.stringify(result.body), /test-token|test-secret/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
