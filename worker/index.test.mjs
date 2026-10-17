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

function request(body, { method = "POST", token = "test-access-token-1234567890123456789012345678", requestOrigin = origin, url = "https://worker.example/" } = {}) {
  const headers = new Headers({ Origin: requestOrigin, "CF-Connecting-IP": "203.0.113.10" });
  if (token !== null) headers.set("Authorization", "Bearer " + token);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  return new Request(url, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}


async function runWorker(req, testEnv, { authHandler } = {}) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    if (String(url).startsWith("https://auth.chi.qzz.io/api/userinfo?")) {
      if (authHandler) return authHandler(url, options);
      const token = options?.headers?.Authorization || "";
      if (token === "Bearer test-access-token-1234567890123456789012345678") {
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

test("rejects a missing or invalid Chi Auth access token", async () => {
  const missing = await runWorker(request({}, { token: null }), env);
  const incorrect = await runWorker(request({}, { token: "invalid-access-token-1234567890123456789012345" }), env);
  assert.equal(missing.status, 401);
  assert.equal(incorrect.status, 401);
});

test("fails closed when Chi Auth is unavailable without consuming dispatch quota", async () => {
  let dispatchLimitCalls = 0;
  let githubCalls = 0;
  const testEnv = {
    ...env,
    DISPATCH_RATE_LIMITER: { async limit() { dispatchLimitCalls++; return { success: true }; } },
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    githubCalls++;
    return new Response(null, { status: 204 });
  };
  try {
    const response = await runWorker(request({}), testEnv, {
      authHandler: async () => { throw new TypeError("private auth outage detail"); },
    });
    const result = await jsonResponse(response);
    assert.equal(response.status, 503);
    assert.match(result.body.error, /Chi Auth is temporarily unavailable/);
    assert.doesNotMatch(JSON.stringify(result.body), /private auth outage detail/);
    assert.equal(dispatchLimitCalls, 0);
    assert.equal(githubCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects an unexpected Chi Auth identity before dispatch", async () => {
  let dispatchLimitCalls = 0;
  let githubCalls = 0;
  const testEnv = {
    ...env,
    DISPATCH_RATE_LIMITER: { async limit() { dispatchLimitCalls++; return { success: true }; } },
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    githubCalls++;
    return new Response(null, { status: 204 });
  };
  try {
    const response = await runWorker(request({}), testEnv, {
      authHandler: async () => new Response(JSON.stringify({ sub: "someone-else", aud: clientId }), {
        status: 200, headers: { "Content-Type": "application/json" },
      }),
    });
    assert.equal(response.status, 403);
    assert.equal(dispatchLimitCalls, 0);
    assert.equal(githubCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects dispatch to a workflow outside the allowlist", async () => {
  const response = await runWorker(request({ repository: "attacker/repo", workflow: "deploy.yml" }), env);
  assert.equal(response.status, 403);
});

test("rejects non-main refs and unsupported inputs", async () => {
  const wrongRef = await runWorker(request({ ref: "feature" }), env);
  const wrongInput = await runWorker(request({ repository: "tsai97216/status", workflow: "update-status.yml", inputs: { arbitrary: "value" } }), env);
  const oversizedInput = await runWorker(request({ repository: "tsai97216/chi-source", workflow: "main.yml", inputs: { app: "x".repeat(101) } }), env);
  assert.equal(wrongRef.status, 400);
  assert.equal(wrongInput.status, 400);
  assert.equal(oversizedInput.status, 400);
  assert.match((await oversizedInput.json()).error, /at most 100 characters/);
});

test("rejects request bodies larger than 16 KiB before parsing or dispatch", async () => {
  let dispatchLimitCalls = 0;
  let githubCalls = 0;
  const testEnv = {
    ...env,
    DISPATCH_RATE_LIMITER: { async limit() { dispatchLimitCalls++; return { success: true }; } },
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    githubCalls++;
    return new Response(null, { status: 204 });
  };
  try {
    const oversized = new Request("https://worker.example/", {
      method: "POST",
      headers: {
        Origin: origin,
        "CF-Connecting-IP": "203.0.113.10",
        Authorization: "Bearer test-access-token-1234567890123456789012345678",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ padding: "x".repeat(16_384) }),
    });
    const response = await runWorker(oversized, testEnv);
    const result = await jsonResponse(response);
    assert.equal(response.status, 413);
    assert.match(result.body.error, /too large/i);
    assert.equal(dispatchLimitCalls, 0);
    assert.equal(githubCalls, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("rejects non-object request bodies instead of triggering the default workflow", async () => {
  const cases = [null, [], "unexpected", 123];
  for (const body of cases) {
    const response = await runWorker(request(body), env);
    assert.equal(response.status, 400, `body ${JSON.stringify(body)} should be rejected`);
    assert.match((await response.json()).error, /Request body must be an object/);
  }
});

test("rejects non-text dispatch selectors before consuming quota", async () => {
  let dispatchLimitCalls = 0;
  const testEnv = {
    ...env,
    DISPATCH_RATE_LIMITER: { async limit() { dispatchLimitCalls++; return { success: true }; } },
  };
  const cases = [
    { repository: { name: "tsai97216/status" } },
    { workflow: ["update-status.yml"] },
    { ref: { branch: "main" } },
  ];

  for (const body of cases) {
    const response = await runWorker(request(body), testEnv);
    assert.equal(response.status, 400);
    assert.match((await response.json()).error, /must be text/);
  }
  assert.equal(dispatchLimitCalls, 0);
});

test("does not expose or log GitHub upstream response bodies", async () => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  const secretLikeBody = "upstream-private-detail ghp_example-secret-value";
  const logged = [];
  globalThis.fetch = async () => new Response(secretLikeBody, { status: 500 });
  console.error = (...args) => logged.push(args.join(" "));
  try {
    const response = await runWorker(request({}), env);
    const result = await jsonResponse(response);
    assert.equal(response.status, 502);
    assert.match(result.body.error, /HTTP 500/);
    assert.doesNotMatch(JSON.stringify(result.body), /upstream-private-detail|ghp_example-secret-value/);
    assert.doesNotMatch(logged.join(" "), /upstream-private-detail|ghp_example-secret-value/);
    assert.match(logged.join(" "), /GitHub dispatch failed/);
  } finally {
    globalThis.fetch = originalFetch;
    console.error = originalError;
  }
});

test("rejects malformed and wrongly typed workflow inputs", async () => {
  const wrongType = await runWorker(request({
    repository: "tsai97216/chi-source",
    workflow: "main.yml",
    inputs: { app: 123 },
  }), env);
  const arrayInputs = await runWorker(request({
    repository: "tsai97216/chi-source",
    workflow: "main.yml",
    inputs: ["all"],
  }), env);
  const nullInputs = await runWorker(request({
    repository: "tsai97216/chi-source",
    workflow: "main.yml",
    inputs: null,
  }), env);

  assert.equal(wrongType.status, 400);
  assert.match((await wrongType.json()).error, /must be text/);
  assert.equal(arrayInputs.status, 400);
  assert.match((await arrayInputs.json()).error, /object/);
  assert.equal(nullInputs.status, 400);
  assert.match((await nullInputs.json()).error, /object/);
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
    assert.doesNotMatch(JSON.stringify(result.body), /test-token|test-access-token-1234567890123456789012345678/);
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
  assert.deepEqual([...new Set(result.body.workflows.map(item => item.group))].sort((a, b) => a.localeCompare(b, "zh-Hant")), [...["自動化", "更新", "維護"]].sort((a, b) => a.localeCompare(b, "zh-Hant")));
  assert.equal(result.body.workflows.length, 7);
  assert.ok(result.body.workflows.every(item => item.available !== false));
  assert.ok(result.body.workflows.every(item => typeof item.description === "string" && item.description.length > 0));
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
    assert.doesNotMatch(JSON.stringify(result.body), /simulated timeout|test-token|test-access-token-1234567890123456789012345678/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
