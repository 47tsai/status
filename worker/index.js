const ALLOWED_ORIGIN = "https://status.chi.qzz.io";
const CHI_AUTH_CLIENT_ID = "DZT0NzjdlmwxReZ47kOVdNVV42YOtCV1";
const CHI_AUTH_USERINFO_URL = "https://auth.chi.qzz.io/api/userinfo";
const DEFAULT_REPOSITORY = "tsai97216/status";
const DEFAULT_WORKFLOW = "update-status.yml";

// Keep this catalog aligned with the projects displayed in status.json.
// Only these workflows can be triggered by this Worker.
const WORKFLOWS = [
  { repository: "tsai97216/status", workflow: "update-status.yml", name: "Status 狀態資料更新", description: "更新狀態總覽使用的專案資料。", project: "status", group: "維護", inputs: [] },
  { repository: "tsai97216/chi-source", workflow: "main.yml", name: "Chi Source 更新", description: "更新主來源的 App 資料；all 代表全部項目。", project: "chi-source", group: "更新", inputs: [{ name: "app", label: "指定 App（all 代表全部）", type: "string", required: false, default: "all", maxLength: 100 }] },
  { repository: "tsai97216/chi-source-personal", workflow: "main.yml", name: "Chi Source Personal 更新", description: "更新個人來源的 App 資料；all 代表全部項目。", project: "chi-source-personal", group: "更新", inputs: [{ name: "app", label: "指定 App（all 代表全部）", type: "string", required: false, default: "all", maxLength: 100 }] },
  { repository: "tsai97216/free-game", workflow: "free-game.yml", name: "限免遊戲通知更新", description: "手動重新執行限免遊戲資料與通知流程。", project: "free-game", group: "更新", inputs: [] },
  { repository: "tsai97216/sc-auto-claim", workflow: "daily.yml", name: "荒野亂鬥自動領取", description: "手動執行設定好的自動領取流程。", project: "sc-auto-claim", group: "自動化", inputs: [] },
  { repository: "tsai97216/bahasign", workflow: "actions.yml", name: "巴哈姆特自動簽到", description: "手動執行巴哈姆特簽到流程。", project: "bahasign", group: "自動化", inputs: [] },
  { repository: "tsai97216/apktwsign", workflow: "checkin.yml", name: "APK.TW 自動簽到", description: "手動執行 APK.TW 簽到流程。", project: "apktwsign", group: "自動化", inputs: [] },
];

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Vary": "Origin",
    },
  });
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    if (origin !== ALLOWED_ORIGIN) return json({ ok: false, error: "Origin not allowed." }, 403);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: {
        "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
      }});
    }

    if (!["GET", "POST"].includes(request.method)) return json({ ok: false, error: "Method not allowed." }, 405);

    // Rate-limit requests by client IP before checking credentials to slow down key guessing.
    // Cloudflare's limiter is approximate and scoped to a Cloudflare location.
    const clientIp = request.headers.get("CF-Connecting-IP") || "missing-ip";
    const ipAllowed = await checkRateLimit(env.IP_RATE_LIMITER, clientIp);
    if (ipAllowed === null) return json({ ok: false, error: "Rate limiter is unavailable." }, 503);
    if (!ipAllowed) return json({ ok: false, error: "Too many requests. Please wait and try again." }, 429);

    if (!env.GITHUB_TOKEN) return json({ ok: false, error: "Worker secrets are not configured." }, 503);

    const authorization = request.headers.get("Authorization") || "";
    const tokenMatch = authorization.match(/^Bearer ([A-Za-z0-9_-]{40,80})$/);
    if (!tokenMatch) return json({ ok: false, error: "Chi Auth login is required." }, 401);
    let identity;
    let identityVerified = false;
    for (let attempt = 1; attempt <= 2; attempt++) {
      let identityResponse;
      try {
        const identityUrl = CHI_AUTH_USERINFO_URL + "?client_id=" + encodeURIComponent(CHI_AUTH_CLIENT_ID);
        const makeIdentityOptions = () => ({
          headers: { Authorization: "Bearer " + tokenMatch[1], Accept: "application/json" },
          cache: "no-store",
          redirect: "error",
          // AbortSignal is one-shot. Each independent request must get its own timeout.
          signal: AbortSignal.timeout(8000),
        });
        if (env.CHI_AUTH && typeof env.CHI_AUTH.fetch === "function") {
          try {
            identityResponse = await env.CHI_AUTH.fetch(identityUrl, makeIdentityOptions());
          } catch (bindingError) {
            console.warn("Chi Auth service binding failed; trying public endpoint", {
              name: bindingError?.name || "unknown",
              message: typeof bindingError?.message === "string"
                ? bindingError.message.replace(/[^A-Za-z0-9 ._:/-]/g, "").slice(0, 100)
                : "no message",
            });
            identityResponse = await fetch(identityUrl, makeIdentityOptions());
          }
        } else {
          identityResponse = await fetch(identityUrl, makeIdentityOptions());
        }
      } catch (error) {
        const upstreamErrorName = typeof error?.name === "string" && /^[A-Za-z][A-Za-z0-9]{0,40}$/.test(error.name)
          ? error.name
          : "UnknownError";
        const upstreamErrorMessage = typeof error?.message === "string"
          ? error.message.replace(/[^A-Za-z0-9 ._:/-]/g, "").slice(0, 100)
          : "";
        console.error("Chi Auth identity request failed", { attempt, name: upstreamErrorName, message: upstreamErrorMessage || "no message" });
        if (attempt < 2) continue;
        return json({
          ok: false,
          error: "Chi Auth is temporarily unavailable. Please retry. (upstream connection: " + upstreamErrorName + ")",
        }, 503);
      }

      if (identityResponse.status >= 500) {
        const upstreamError = await identityResponse.clone().json().catch(() => null);
        const diagnosticStage = typeof upstreamError?.debug === "string" &&
          /^[a-z_]{1,64}$/.test(upstreamError.debug) ? upstreamError.debug : null;
        console.error("Chi Auth identity service returned a server error", {
          attempt, status: identityResponse.status, diagnosticStage,
        });
        if (attempt < 2) continue;
        return json({
          ok: false,
          error: "Chi Auth is temporarily unavailable. Please retry." +
            (diagnosticStage ? " (diagnostic stage: " + diagnosticStage + ")" : ""),
        }, 503);
      }
      if (!identityResponse.ok) return json({ ok: false, error: "Chi Auth token is invalid or expired." }, 401);

      try {
        identity = await identityResponse.json();
        identityVerified = true;
        break;
      } catch (error) {
        console.error("Chi Auth identity response was not valid JSON", { attempt, name: error?.name || "unknown" });
        if (attempt >= 2) return json({ ok: false, error: "Chi Auth is temporarily unavailable. Please retry." }, 503);
      }
    }
    if (!identityVerified) return json({ ok: false, error: "Chi Auth is temporarily unavailable. Please retry." }, 503);
    if (identity?.sub !== "chi-owner" || identity?.aud !== CHI_AUTH_CLIENT_ID) {
      return json({ ok: false, error: "Chi Auth identity or audience check failed." }, 403);
    }

    if (request.method === "GET") {
      const url = new URL(request.url);
      if (url.searchParams.get("action") !== "catalog") return json({ ok: false, error: "Unknown action." }, 400);
      return json({ ok: true, workflows: WORKFLOWS });
    }

    const contentType = request.headers.get("Content-Type") || "";
    if (!/^application\/json(?:\s*;|\s*$)/i.test(contentType)) {
      return json({ ok: false, error: "Content-Type must be application/json." }, 415);
    }

    const parsedBody = await readJsonBody(request, 16_384);
    if (parsedBody.tooLarge) return json({ ok: false, error: "Request body is too large." }, 413);
    if (!parsedBody.ok) return json({ ok: false, error: "Invalid JSON body." }, 400);
    const body = parsedBody.body;
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      return json({ ok: false, error: "Request body must be an object." }, 400);
    }

    for (const field of ["repository", "workflow", "ref"]) {
      if (Object.prototype.hasOwnProperty.call(body, field) && typeof body[field] !== "string") {
        return json({ ok: false, error: `Field ${field} must be text.` }, 400);
      }
    }

    const repository = body.repository || DEFAULT_REPOSITORY;
    const workflow = body.workflow || DEFAULT_WORKFLOW;
    const ref = body.ref || "main";
    if (ref !== "main") return json({ ok: false, error: "Only the main branch can be triggered." }, 400);

    const entry = WORKFLOWS.find(item => item.available !== false && item.repository === repository && item.workflow === workflow);
    if (!entry) return json({ ok: false, error: "This workflow is not in the approved status-project allowlist." }, 403);

    const suppliedInputs = body && Object.prototype.hasOwnProperty.call(body, "inputs") ? body.inputs : {};
    if (!suppliedInputs || typeof suppliedInputs !== "object" || Array.isArray(suppliedInputs)) {
      return json({ ok: false, error: "Inputs must be an object." }, 400);
    }
    const allowedInputNames = new Set(entry.inputs.map(input => input.name));
    for (const key of Object.keys(suppliedInputs)) {
      if (!allowedInputNames.has(key)) return json({ ok: false, error: `Unsupported input: ${key}` }, 400);
    }

    const inputs = {};
    for (const spec of entry.inputs) {
      const value = Object.prototype.hasOwnProperty.call(suppliedInputs, spec.name) ? suppliedInputs[spec.name] : spec.default;
      if (spec.required && (value === undefined || value === null || String(value).trim() === "")) {
        return json({ ok: false, error: `Missing required input: ${spec.name}` }, 400);
      }
      if (value === undefined || value === null || value === "") continue;
      if (spec.type === "boolean") {
        if (typeof value !== "boolean") return json({ ok: false, error: `Input ${spec.name} must be boolean.` }, 400);
      } else {
        if (typeof value !== "string") return json({ ok: false, error: `Input ${spec.name} must be text.` }, 400);
        if (Number.isInteger(spec.maxLength) && value.length > spec.maxLength) return json({ ok: false, error: `Input ${spec.name} must be at most ${spec.maxLength} characters.` }, 400);
        if (spec.type === "choice" && !spec.options.includes(value)) return json({ ok: false, error: `Invalid option for ${spec.name}.` }, 400);
      }
      inputs[spec.name] = value;
    }

    // Charge the dispatch quota only after the request passes validation.
    const dispatchAllowed = await checkRateLimit(env.DISPATCH_RATE_LIMITER, "authenticated-workflow-dispatch");
    if (dispatchAllowed === null) return json({ ok: false, error: "Rate limiter is unavailable." }, 503);
    if (!dispatchAllowed) return json({ ok: false, error: "Workflow trigger limit reached. Wait one minute before trying again." }, 429);

    let response;
    try {
      response = await fetch(`https://api.github.com/repos/${repository}/actions/workflows/${workflow}/dispatches`, {
        method: "POST",
        headers: {
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "Chi-Status-Trigger",
          "Content-Type": "application/json",
        },
        redirect: "error",
        body: JSON.stringify({ ref, inputs }),
        signal: AbortSignal.timeout(10_000),
      });
    } catch (error) {
      console.error("GitHub dispatch request failed", repository, workflow, error?.name || "unknown");
      return json({ ok: false, error: error?.name === "TimeoutError"
        ? "GitHub API request timed out; dispatch status is unknown. Check the GitHub Actions run history before retrying."
        : "GitHub API connection failed; dispatch status is unknown. Check the GitHub Actions run history before retrying." }, 502);
    }

    if (response.status !== 204) {
      // Log only stable metadata; never copy upstream response bodies into logs.
      console.error("GitHub dispatch failed", repository, workflow, response.status);
      return json({ ok: false, error: response.status === 401 || response.status === 403
        ? "GitHub rejected the token or repository permission. Check token repository access and Actions: Read and write."
        : `GitHub API returned HTTP ${response.status}.` }, 502);
    }

    return json({ ok: true, message: "Workflow dispatch accepted.", repository, workflow, ref }, 202);
  },
};

async function readJsonBody(request, maxBytes) {
  if (!request.body) return { ok: false };

  const reader = request.body.getReader();
  const chunks = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > maxBytes) {
        try { await reader.cancel(); } catch {}
        return { ok: false, tooLarge: true };
      }
      chunks.push(value);
    }
  } catch {
    return { ok: false };
  }

  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    return { ok: true, body: JSON.parse(new TextDecoder().decode(bytes)) };
  } catch {
    return { ok: false };
  }
}

async function checkRateLimit(limiter, key) {
  try {
    const result = await limiter.limit({ key });
    return result?.success === true;
  } catch (error) {
    console.error("Rate limiter failed", error?.name || "unknown");
    return null;
  }
}

