import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./index.js";

const allowRateLimit = { async limit() { return { success: true }; } };
const env = {
  GITHUB_TOKEN: "test-token",
  IP_RATE_LIMITER: allowRateLimit,
  DISPATCH_RATE_LIMITER: allowRateLimit,
};
const origin = "https://status.chi.qzz.io";

const clientId = "DZT0NzjdlmwxReZ47kOVdNVV42YOtCV1";

function request(body, { method = "POST", token = "test-access-token", requestOrigin = origin, url = "https://worker.example/" } = {}) {
  const headers = new Headers({ Origin: requestOrigin, "CF-Connecting-IP": "203.0.113.10" });
  if (token !== null) headers.set("Authorization", "Bearer " + token);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  return new Request(url, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}


async function runWorker(req, testEnv) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (String(url).startsWith("https://auth.chi.qzz.io/api/userinfo?")) {
      const token = options?.headers?.Authorization || "";
      if (token === "Bearer test-access-token") {
        return new Response(JSON.stringify({ sub: "chi-owner", aud: clientId }), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ ok: false }), { status: 401 });
    }
    return originalFetch(url, options);
  };
  try { return await worker.fetch(req, testEnv); }
  finally { globalThis.fetch = originalFetch; }
}

async function jsonResponse(response) {
  return { status: response.status, body: await response.json() };
}


test("blocks requests when the client IP rate limit is exceeded", async () => {
  const blockedEnv = {
    ...env,
    IP_RATE_LIMITER: { async limit() { return { success: false }; } },
  };
  const response = await runWorker(request({}), blockedEnv);
  const result = await jsonResponse(response);
  assert.equal(response.status, 429);
  assert.match(result.body.error, /Too many requests/);
});

test("blocks authenticated workflow dispatches over the dispatch quota", async () => {
  const blockedEnv = {
    ...env,
    DISPATCH_RATE_LIMITER: { async limit() { return { success: false }; } },
  };
  const response = await runWorker(request({}), blockedEnv);
  const result = await jsonResponse(response);
  assert.equal(response.status, 429);
  assert.match(result.body.error, /Workflow trigger limit/);
});

test("fails closed if the rate limiter is unavailable", async () => {
  const brokenEnv = {
    ...env,
    IP_RATE_LIMITER: { async limit() { throw new Error("private infrastructure detail"); } },
  };
  const response = await runWorker(request({}), brokenEnv);
  const result = await jsonResponse(response);
  assert.equal(response.status, 503);
  assert.doesNotMatch(JSON.stringify(result.body), /private infrastructure detail/);
});

test("rejects requests with an unapproved Origin", async () => {
  const response = await runWorker(request({}, { requestOrigin: "https://evil.example" }), env);
  assert.equal(response.status, 403);
});

test("rejects a missing or incorrect trigger key", async () => {
  const missing = await runWorker(request({}, { token: null }), env);
  const incorrect = await runWorker(request({}, { token: "invalid-access-token" }), env);
  assert.equal(missing.status, 401);
  assert.equal(incorrect.status, 401);
});

test("rejects dispatch to a workflow outside the allowlist", async () => {
  const response = await runWorker(request({ repository: "attacker/repo", workflow: "deploy.yml" }), env);
  assert.equal(response.status, 403);
});

test("rejects non-main refs and unsupported inputs", async () => {
  const wrongRef = await runWorker(request({ ref: "feature" }), env);
  const wrongInput = await runWorker(request({ repository: "tsai97216/status", workflow: "update-status.yml", inputs: { arbitrary: "value" } }), env);
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
    const response = await runWorker(request({
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
    const response = await runWorker(request({}), env);
    const result = await jsonResponse(response);
    assert.equal(response.status, 502);
    assert.equal(result.body.ok, false);
    assert.match(result.body.error, /Could not reach/);
    assert.doesNotMatch(JSON.stringify(result.body), /test-token|test-access-token/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("handles CORS preflight without requiring credentials or consuming rate limits", async () => {
  let ipLimitCalls = 0;
  let dispatchLimitCalls = 0;
  const testEnv = {
    ...env,
    IP_RATE_LIMITER: { async limit() { ipLimitCalls++; return { success: true }; } },
    DISPATCH_RATE_LIMITER: { async limit() { dispatchLimitCalls++; return { success: true }; } },
  };
  const response = await runWorker(request(undefined, { method: "OPTIONS", key: null }), testEnv);
  assert.equal(response.status, 204);
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), origin);
  assert.match(response.headers.get("Access-Control-Allow-Headers") || "", /Authorization/);
  assert.equal(ipLimitCalls, 0);
  assert.equal(dispatchLimitCalls, 0);
});

test("catalog GET does not consume the workflow-dispatch quota", async () => {
  let dispatchLimitCalls = 0;
  const testEnv = {
    ...env,
    DISPATCH_RATE_LIMITER: { async limit() { dispatchLimitCalls++; return { success: true }; } },
  };
  const response = await runWorker(request(undefined, {
    method: "GET",
    url: "https://worker.example/?action=catalog",
  }), testEnv);
  const result = await jsonResponse(response);
  assert.equal(response.status, 200);
  assert.equal(result.body.ok, true);
  assert.ok(Array.isArray(result.body.workflows));
  assert.equal(dispatchLimitCalls, 0);
});

test("invalid authenticated POST requests do not consume the workflow-dispatch quota", async () => {
  let dispatchLimitCalls = 0;
  const testEnv = {
    ...env,
    DISPATCH_RATE_LIMITER: { async limit() { dispatchLimitCalls++; return { success: true }; } },
  };
  const response = await runWorker(request({
    repository: "attacker/repo",
    workflow: "deploy.yml",
    ref: "main",
  }), testEnv);
  assert.equal(response.status, 403);
  assert.equal(dispatchLimitCalls, 0);
});

test("returns a specific safe error when the GitHub API request times out", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new DOMException("simulated timeout", "TimeoutError"); };
  try {
    const response = await runWorker(request({}), env);
    const result = await jsonResponse(response);
    assert.equal(response.status, 502);
    assert.equal(result.body.ok, false);
    assert.match(result.body.error, /timed out/i);
    assert.doesNotMatch(JSON.stringify(result.body), /simulated timeout|test-token|test-access-token/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
