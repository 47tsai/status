const REPOSITORY = "tsai97216/status";
const WORKFLOW = "update-status.yml";
const ALLOWED_ORIGIN = "https://status.chi.qzz.io";

function json(body, status = 200, origin = ALLOWED_ORIGIN) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Trigger-Key",
      "Vary": "Origin",
    },
  });
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    if (origin !== ALLOWED_ORIGIN) {
      return json({ ok: false, error: "Origin not allowed." }, 403, ALLOWED_ORIGIN);
    }

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, X-Trigger-Key",
          "Access-Control-Max-Age": "86400",
          "Vary": "Origin",
        },
      });
    }

    if (request.method !== "POST") {
      return json({ ok: false, error: "Method not allowed." }, 405);
    }

    if (!env.GITHUB_TOKEN || !env.TRIGGER_SECRET) {
      return json({ ok: false, error: "Worker secrets are not configured." }, 503);
    }

    const suppliedKey = request.headers.get("X-Trigger-Key") || "";
    if (!constantTimeEqual(suppliedKey, env.TRIGGER_SECRET)) {
      return json({ ok: false, error: "Invalid trigger key." }, 401);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "Invalid JSON body." }, 400);
    }
    if (body?.ref !== "main") {
      return json({ ok: false, error: "Only the main branch can be triggered." }, 400);
    }

    const response = await fetch(
      `https://api.github.com/repos/${REPOSITORY}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "Chi-Status-Trigger",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main" }),
      },
    );

    if (response.status !== 204) {
      const detail = (await response.text()).slice(0, 500);
      console.error("GitHub dispatch failed", response.status, detail);
      return json({
        ok: false,
        error: response.status === 401 || response.status === 403
          ? "GitHub rejected the token. Check token permissions and repository access."
          : `GitHub API returned HTTP ${response.status}.`,
      }, 502);
    }

    return json({ ok: true, message: "Workflow dispatch accepted." }, 202);
  },
};

function constantTimeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
