const ALLOWED_ORIGIN = "https://status.chi.qzz.io";
const DEFAULT_REPOSITORY = "tsai97216/status";
const DEFAULT_WORKFLOW = "update-status.yml";

const WORKFLOWS = [
  { repository: "tsai97216/bahasign", workflow: "actions.yml", name: "Baha 每日簽到", group: "自動化", inputs: [] },
  { repository: "tsai97216/chi-source", workflow: "main.yml", name: "更新 Chi Source", group: "來源維護", inputs: [{ name: "app", label: "指定 App（all 代表全部）", type: "string", required: false, default: "all" }] },
  { repository: "tsai97216/sc-auto-claim", workflow: "daily.yml", name: "SC 自動領取", group: "自動化", inputs: [] },
  { repository: "tsai97216/apktwsign", workflow: "checkin.yml", name: "APK.TW 簽到", group: "自動化", inputs: [] },
  { repository: "tsai97216/nav-n", workflow: "import-nav-old.yml", name: "NAV 資料驗證", group: "驗證", inputs: [] },
  { repository: "tsai97216/merch-old", workflow: "deploy.yml", name: "周邊收藏網（舊版）部署", group: "部署", inputs: [], danger: "會部署 GitHub Pages 網站。" },
  { repository: "tsai97216/merch", workflow: "verify.yml", name: "周邊收藏網驗證", group: "驗證", inputs: [] },
  { repository: "tsai97216/free-game", workflow: "free-game.yml", name: "限免遊戲通知更新", group: "內容更新", inputs: [] },
  { repository: "tsai97216/Brave-Free-Origin", workflow: "ci.yml", name: "Brave-Free-Origin 驗證", group: "驗證", inputs: [] },
  { repository: "tsai97216/Brave-Free-Origin", workflow: "release.yml", name: "Brave-Free-Origin 發布流程", group: "發布", inputs: [{ name: "tag", label: "既有 Tag（留空則 dry run）", type: "string", required: false, default: "" }, { name: "dry_run", label: "僅測試，不發布", type: "boolean", required: false, default: true }], danger: "正式發布前請保持「僅測試」開啟；關閉後可能建立或更新 GitHub Release。" },
  { repository: "tsai97216/spoti.pw", workflow: "build-ipa.yml", name: "Spoti.pw IPA 建置", group: "建置", inputs: [{ name: "ipa_url", label: "解密 IPA 的直接下載網址", type: "string", required: true, default: "" }, { name: "upload_method", label: "輸出方式", type: "choice", required: false, default: "artifacts", options: ["artifacts", "filebin", "both"] }] },
  { repository: "tsai97216/tsai97216.github.io", workflow: "ci.yml", name: "個人網站 CI 驗證", group: "驗證", inputs: [] },
  { repository: "tsai97216/tsai97216.github.io", workflow: "deploy.yml", name: "個人網站部署", group: "部署", inputs: [], danger: "會建置並部署正式網站。" },
  { repository: "tsai97216/h", workflow: "ci.yml", name: "H 工具箱 CI 驗證", group: "驗證", inputs: [] },
  { repository: "tsai97216/h", workflow: "deploy-pages.yml", name: "H 工具箱 Pages 部署", group: "部署", inputs: [], danger: "會部署正式網站。" },
  { repository: "tsai97216/h", workflow: "deploy-worker.yml", name: "H 工具箱 Worker 部署", group: "部署", inputs: [], danger: "會部署 Cloudflare Worker。" },
  { repository: "tsai97216/chi-source-personal", workflow: "main.yml", name: "更新個人 Chi Source", group: "來源維護", inputs: [{ name: "app", label: "指定 App（all 代表全部）", type: "string", required: false, default: "all" }] },
  { repository: "tsai97216/status", workflow: "deploy-trigger-worker.yml", name: "Status Worker 部署", group: "部署", inputs: [], danger: "會重新部署觸發 API Worker。" },
  { repository: "tsai97216/status", workflow: "update-status.yml", name: "Status 狀態更新", group: "維護", inputs: [] },
];

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Trigger-Key",
      "Vary": "Origin",
    },
  });
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    if (origin !== ALLOWED_ORIGIN) {
      return json({ ok: false, error: "Origin not allowed." }, 403);
    }

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, X-Trigger-Key",
          "Access-Control-Max-Age": "86400",
          "Vary": "Origin",
        },
      });
    }

    if (!["GET", "POST"].includes(request.method)) {
      return json({ ok: false, error: "Method not allowed." }, 405);
    }
    if (!env.GITHUB_TOKEN || !env.TRIGGER_SECRET) {
      return json({ ok: false, error: "Worker secrets are not configured." }, 503);
    }

    const suppliedKey = request.headers.get("X-Trigger-Key") || "";
    if (!constantTimeEqual(suppliedKey, env.TRIGGER_SECRET)) {
      return json({ ok: false, error: "Invalid trigger key." }, 401);
    }

    if (request.method === "GET") {
      const url = new URL(request.url);
      if (url.searchParams.get("action") !== "catalog") {
        return json({ ok: false, error: "Unknown action." }, 400);
      }
      return json({ ok: true, workflows: WORKFLOWS });
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "Invalid JSON body." }, 400);
    }

    // Backward compatibility for the original dashboard refresh button.
    const repository = body?.repository || DEFAULT_REPOSITORY;
    const workflow = body?.workflow || DEFAULT_WORKFLOW;
    const ref = body?.ref || "main";
    if (ref !== "main") {
      return json({ ok: false, error: "Only the main branch can be triggered." }, 400);
    }

    const entry = WORKFLOWS.find(item => item.repository === repository && item.workflow === workflow);
    if (!entry) {
      return json({ ok: false, error: "This workflow is not in the approved allowlist." }, 403);
    }

    const suppliedInputs = body?.inputs ?? {};
    if (!suppliedInputs || typeof suppliedInputs !== "object" || Array.isArray(suppliedInputs)) {
      return json({ ok: false, error: "Inputs must be an object." }, 400);
    }
    const allowedInputNames = new Set(entry.inputs.map(input => input.name));
    for (const key of Object.keys(suppliedInputs)) {
      if (!allowedInputNames.has(key)) {
        return json({ ok: false, error: `Unsupported input: ${key}` }, 400);
      }
    }

    const inputs = {};
    for (const spec of entry.inputs) {
      const value = Object.prototype.hasOwnProperty.call(suppliedInputs, spec.name)
        ? suppliedInputs[spec.name]
        : spec.default;
      if (spec.required && (value === undefined || value === null || String(value).trim() === "")) {
        return json({ ok: false, error: `Missing required input: ${spec.name}` }, 400);
      }
      if (value === undefined || value === null || value === "") continue;
      if (spec.type === "boolean") {
        if (typeof value !== "boolean") return json({ ok: false, error: `Input ${spec.name} must be boolean.` }, 400);
      } else {
        if (typeof value !== "string") return json({ ok: false, error: `Input ${spec.name} must be text.` }, 400);
        if (spec.type === "choice" && !spec.options.includes(value)) {
          return json({ ok: false, error: `Invalid option for ${spec.name}.` }, 400);
        }
      }
      inputs[spec.name] = value;
    }

    const response = await fetch(
      `https://api.github.com/repos/${repository}/actions/workflows/${workflow}/dispatches`,
      {
        method: "POST",
        headers: {
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "Chi-Status-Trigger",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref, inputs }),
      },
    );

    if (response.status !== 204) {
      const detail = (await response.text()).slice(0, 500);
      console.error("GitHub dispatch failed", repository, workflow, response.status, detail);
      return json({
        ok: false,
        error: response.status === 401 || response.status === 403
          ? "GitHub rejected the token or repository permission. Check token access and Actions: Read and write."
          : `GitHub API returned HTTP ${response.status}.`,
      }, 502);
    }

    return json({ ok: true, message: "Workflow dispatch accepted.", repository, workflow, ref }, 202);
  },
};

function constantTimeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
