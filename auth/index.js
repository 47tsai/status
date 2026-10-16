import {
  generateAuthenticationOptions,
  generateRegistrationOptions,
  verifyAuthenticationResponse,
  verifyRegistrationResponse,
} from "@simplewebauthn/server";

const RP_ID = "chi.qzz.io";
const RP_NAME = "Chi";
const ORIGIN = "https://chi.qzz.io";
const SESSION_TTL_SECONDS = 60 * 60 * 12;
const CEREMONY_TTL_SECONDS = 5 * 60;

const PAGE = `<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Chi Auth</title>
<style>
:root{font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light dark}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:Canvas;color:CanvasText}
main{width:min(100%,440px);border:1px solid color-mix(in srgb,CanvasText 15%,transparent);border-radius:22px;padding:28px;box-shadow:0 18px 60px #00000012}
.mark{font-size:13px;letter-spacing:.14em;text-transform:uppercase;opacity:.65}h1{margin:10px 0 6px;font-size:30px}p{line-height:1.6;opacity:.78}.field{display:grid;gap:7px;margin:20px 0}label{font-size:14px}input{width:100%;padding:12px 13px;border:1px solid color-mix(in srgb,CanvasText 22%,transparent);border-radius:11px;background:Canvas;color:CanvasText;font:inherit}
button{width:100%;padding:12px 14px;border:0;border-radius:11px;background:#356ae6;color:white;font:inherit;font-weight:650;cursor:pointer;margin-top:10px}button.secondary{background:color-mix(in srgb,CanvasText 9%,Canvas);color:CanvasText}button:disabled{opacity:.55;cursor:wait}
#status{margin-top:18px;padding:12px;border-radius:10px;background:color-mix(in srgb,CanvasText 6%,Canvas);font-size:14px;white-space:pre-wrap;overflow-wrap:anywhere}.muted{font-size:13px;opacity:.62;margin-top:20px}
</style>
</head>
<body><main>
<div class="mark">C◆ / Identity</div><h1>Chi Auth</h1>
<p>Chi 專案共用的身分驗證中心。使用 Passkey 登入，不會把私鑰交給網站。</p>
<div id="setup" class="field" hidden><label for="setupSecret">首次設定碼</label><input id="setupSecret" type="password" autocomplete="current-password" placeholder="輸入一次性設定碼"></div>
<button id="register" hidden>建立第一把 Passkey</button>
<button id="login">使用 Passkey 登入</button>
<button id="logout" class="secondary" hidden>登出</button>
<div id="status" role="status" aria-live="polite">正在檢查驗證服務…</div>
<p class="muted">目前為驗證核心初版，尚未開放其他 Chi 專案的單一登入。請勿把此頁視為已完成的正式 SSO。</p>
</main>
<script type="module">
const $ = (id) => document.getElementById(id);
const status = $("status");
function say(message){status.textContent=message}
function decode(value){const s=value.replace(/-/g,"+").replace(/_/g,"/");const padded=s+"=".repeat((4-s.length%4)%4);return Uint8Array.from(atob(padded),c=>c.charCodeAt(0))}
function encode(value){return btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/g,"")}
async function api(path,body){const response=await fetch("/auth/api/"+path,{method:body===undefined?"GET":"POST",headers:body===undefined?{}:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body),credentials:"same-origin",cache:"no-store"});const data=await response.json().catch(()=>({error:"伺服器回應格式錯誤"}));if(!response.ok)throw new Error(data.error||"請求失敗");return data}
function registrationJSON(credential){return {id:credential.id,rawId:encode(credential.rawId),type:credential.type,authenticatorAttachment:credential.authenticatorAttachment,response:{clientDataJSON:encode(credential.response.clientDataJSON),attestationObject:encode(credential.response.attestationObject),transports:credential.response.getTransports?.()||[]},clientExtensionResults:credential.getClientExtensionResults()}}
function authenticationJSON(credential){return {id:credential.id,rawId:encode(credential.rawId),type:credential.type,authenticatorAttachment:credential.authenticatorAttachment,response:{clientDataJSON:encode(credential.response.clientDataJSON),authenticatorData:encode(credential.response.authenticatorData),signature:encode(credential.response.signature),userHandle:credential.response.userHandle?encode(credential.response.userHandle):null},clientExtensionResults:credential.getClientExtensionResults()}}
async function refresh(){try{const s=await api("session");$("setup").hidden=s.initialized;$("register").hidden=s.initialized;$("login").hidden=!s.initialized||s.authenticated;$("logout").hidden=!s.authenticated;say(s.authenticated?"已登入 Chi Auth。此登入目前只限驗證中心本身。":s.initialized?"尚未登入，請使用已註冊的 Passkey。":"尚未設定 Passkey，請先輸入首次設定碼。")}catch(e){say(e.message)}}
$("register").addEventListener("click",async()=>{const button=$("register");button.disabled=true;try{if(!window.PublicKeyCredential)throw new Error("此瀏覽器不支援 WebAuthn");const start=await api("register/options",{setupSecret:$("setupSecret").value});const options={...start.options,challenge:decode(start.options.challenge),user:{...start.options.user,id:decode(start.options.user.id)},excludeCredentials:(start.options.excludeCredentials||[]).map(c=>({...c,id:decode(c.id)}))};const credential=await navigator.credentials.create({publicKey:options});if(!credential)throw new Error("Passkey 建立已取消");await api("register/verify",{ceremonyId:start.ceremonyId,credential:registrationJSON(credential)});$("setupSecret").value="";say("Passkey 已建立。");await refresh()}catch(e){say(e.message||"建立 Passkey 失敗")}finally{button.disabled=false}});
$("login").addEventListener("click",async()=>{const button=$("login");button.disabled=true;try{if(!window.PublicKeyCredential)throw new Error("此瀏覽器不支援 WebAuthn");const start=await api("login/options");const options={...start.options,challenge:decode(start.options.challenge),allowCredentials:(start.options.allowCredentials||[]).map(c=>({...c,id:decode(c.id)}))};const credential=await navigator.credentials.get({publicKey:options});if(!credential)throw new Error("Passkey 登入已取消");await api("login/verify",{ceremonyId:start.ceremonyId,credential:authenticationJSON(credential)});say("登入成功。");await refresh()}catch(e){say(e.message||"Passkey 登入失敗")}finally{button.disabled=false}});
$("logout").addEventListener("click",async()=>{try{await api("logout",{});await refresh()}catch(e){say(e.message)}});
refresh();
</script>
</body></html>`;

function json(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      ...extraHeaders,
    },
  });
}

function noStoreHtml() {
  return new Response(PAGE, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
      "Permissions-Policy": "publickey-credentials-get=(self), publickey-credentials-create=(self)",
    },
  });
}

function getCookie(request, name) {
  const cookie = request.headers.get("Cookie") || "";
  for (const part of cookie.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return rest.join("=");
  }
  return "";
}

function randomToken(bytes = 32) {
  const value = crypto.getRandomValues(new Uint8Array(bytes));
  return base64url(value);
}

function base64url(value) {
  let binary = "";
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

async function sha256(value) {
  return base64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length || !a.length) return false;
  let difference = 0;
  for (let i = 0; i < a.length; i++) difference |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return difference === 0;
}

async function countPasskeys(db) {
  const row = await db.prepare("SELECT COUNT(*) AS count FROM passkeys").first();
  return Number(row?.count || 0);
}

async function saveCeremony(db, type, challenge) {
  const ceremonyId = randomToken(24);
  const now = Math.floor(Date.now() / 1000);
  await db.prepare("DELETE FROM ceremonies WHERE expires_at <= ?").bind(now).run();
  await db.prepare("INSERT INTO ceremonies (ceremony_id, ceremony_type, challenge, expires_at, created_at) VALUES (?, ?, ?, ?, ?)")
    .bind(ceremonyId, type, challenge, now + CEREMONY_TTL_SECONDS, now).run();
  return ceremonyId;
}

async function takeCeremony(db, ceremonyId, type) {
  if (typeof ceremonyId !== "string" || ceremonyId.length > 128) return null;
  const now = Math.floor(Date.now() / 1000);
  const row = await db.prepare("SELECT ceremony_id, challenge, expires_at FROM ceremonies WHERE ceremony_id = ? AND ceremony_type = ?")
    .bind(ceremonyId, type).first();
  await db.prepare("DELETE FROM ceremonies WHERE ceremony_id = ?").bind(ceremonyId).run();
  if (!row || Number(row.expires_at) <= now) return null;
  return row;
}

async function createSession(db) {
  const token = randomToken();
  const now = Math.floor(Date.now() / 1000);
  const tokenHash = await sha256(token);
  await db.prepare("DELETE FROM sessions WHERE expires_at <= ?").bind(now).run();
  await db.prepare("INSERT INTO sessions (token_hash, created_at, expires_at) VALUES (?, ?, ?)")
    .bind(tokenHash, now, now + SESSION_TTL_SECONDS).run();
  return token;
}

async function sessionIsValid(request, db) {
  const token = getCookie(request, "__Host-chi_auth_session");
  if (!token) return false;
  const tokenHash = await sha256(token);
  const now = Math.floor(Date.now() / 1000);
  const row = await db.prepare("SELECT token_hash FROM sessions WHERE token_hash = ? AND expires_at > ?")
    .bind(tokenHash, now).first();
  return Boolean(row);
}

function sessionCookie(token, maxAge = SESSION_TTL_SECONDS) {
  return `__Host-chi_auth_session=${token}; Path=/; Max-Age=${maxAge}; Secure; HttpOnly; SameSite=Lax`;
}

async function requireSameOrigin(request) {
  const origin = request.headers.get("Origin");
  return origin === ORIGIN;
}

async function handle(request, env) {
  const url = new URL(request.url);
  const path = url.pathname.replace(/^\/auth(?=\/|$)/, "") || "/";
  if (request.method === "GET" && (path === "/" || path === "")) return noStoreHtml();
  if (request.method === "GET" && path === "/api/health") return json({ ok: true, service: "chi-auth", rpId: RP_ID, phase: "passkey-core" });

  if (path.startsWith("/api/") && request.method !== "GET" && request.method !== "POST") {
    return json({ ok: false, error: "Method not allowed." }, 405);
  }

  if (request.method === "GET" && path === "/api/session") {
    const initialized = await countPasskeys(env.DB) > 0;
    const authenticated = initialized && await sessionIsValid(request, env.DB);
    return json({ ok: true, initialized, authenticated });
  }

  if (request.method === "POST" && path.startsWith("/api/") && !(await requireSameOrigin(request))) {
    return json({ ok: false, error: "Origin not allowed." }, 403);
  }

  if (request.method === "POST" && path === "/api/register/options") {
    const body = await request.json().catch(() => null);
    if (!body || typeof body.setupSecret !== "string" || !safeEqual(body.setupSecret, env.CHI_AUTH_SETUP_SECRET || "")) {
      return json({ ok: false, error: "首次設定碼不正確。" }, 401);
    }
    if (await countPasskeys(env.DB) > 0) return json({ ok: false, error: "Passkey 已完成初始設定，公開註冊已關閉。" }, 409);
    const options = await generateRegistrationOptions({
      rpName: RP_NAME,
      rpID: RP_ID,
      userName: "chi-owner",
      userDisplayName: "Chi Owner",
      attestationType: "none",
      authenticatorSelection: { residentKey: "required", userVerification: "required" },
      supportedAlgorithmIDs: [-7, -257],
    });
    const ceremonyId = await saveCeremony(env.DB, "registration", options.challenge);
    return json({ ok: true, options, ceremonyId });
  }

  if (request.method === "POST" && path === "/api/register/verify") {
    const body = await request.json().catch(() => null);
    if (!body?.credential || typeof body.ceremonyId !== "string") return json({ ok: false, error: "Invalid request." }, 400);
    if (await countPasskeys(env.DB) > 0) return json({ ok: false, error: "Passkey 已完成初始設定。" }, 409);
    const ceremony = await takeCeremony(env.DB, body.ceremonyId, "registration");
    if (!ceremony) return json({ ok: false, error: "設定程序已逾時，請重新開始。" }, 400);
    let verification;
    try {
      verification = await verifyRegistrationResponse({
        response: body.credential,
        expectedChallenge: ceremony.challenge,
        expectedOrigin: ORIGIN,
        expectedRPID: RP_ID,
        requireUserVerification: true,
      });
    } catch {
      return json({ ok: false, error: "Passkey 驗證失敗，請重新嘗試。" }, 400);
    }
    if (!verification.verified || !verification.registrationInfo) return json({ ok: false, error: "Passkey 驗證未通過。" }, 400);
    const { credential, credentialDeviceType, credentialBackedUp } = verification.registrationInfo;
    const now = Math.floor(Date.now() / 1000);
    try {
      await env.DB.prepare("INSERT INTO passkeys (credential_id, public_key, counter, transports_json, device_type, backed_up, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)")
        .bind(credential.id, credential.publicKey, credential.counter, JSON.stringify(credential.transports || []), credentialDeviceType, credentialBackedUp ? 1 : 0, now).run();
    } catch {
      return json({ ok: false, error: "無法儲存 Passkey，請確認資料庫設定。" }, 500);
    }
    const token = await createSession(env.DB);
    return json({ ok: true, verified: true }, 201, { "Set-Cookie": sessionCookie(token) });
  }

  if (request.method === "POST" && path === "/api/login/options") {
    const rows = await env.DB.prepare("SELECT credential_id, transports_json FROM passkeys").all();
    if (!rows.results?.length) return json({ ok: false, error: "尚未設定 Passkey。" }, 409);
    const options = await generateAuthenticationOptions({
      rpID: RP_ID,
      allowCredentials: rows.results.map(row => ({ id: row.credential_id, transports: JSON.parse(row.transports_json || "[]") })),
      userVerification: "required",
    });
    const ceremonyId = await saveCeremony(env.DB, "authentication", options.challenge);
    return json({ ok: true, options, ceremonyId });
  }

  if (request.method === "POST" && path === "/api/login/verify") {
    const body = await request.json().catch(() => null);
    if (!body?.credential || typeof body.ceremonyId !== "string" || typeof body.credential.id !== "string") {
      return json({ ok: false, error: "Invalid request." }, 400);
    }
    const ceremony = await takeCeremony(env.DB, body.ceremonyId, "authentication");
    if (!ceremony) return json({ ok: false, error: "登入程序已逾時，請重新開始。" }, 400);
    const passkey = await env.DB.prepare("SELECT credential_id, public_key, counter, transports_json FROM passkeys WHERE credential_id = ?")
      .bind(body.credential.id).first();
    if (!passkey) return json({ ok: false, error: "找不到這把 Passkey。" }, 401);
    let verification;
    try {
      verification = await verifyAuthenticationResponse({
        response: body.credential,
        expectedChallenge: ceremony.challenge,
        expectedOrigin: ORIGIN,
        expectedRPID: RP_ID,
        requireUserVerification: true,
        credential: {
          id: passkey.credential_id,
          publicKey: new Uint8Array(passkey.public_key),
          counter: Number(passkey.counter),
          transports: JSON.parse(passkey.transports_json || "[]"),
        },
      });
    } catch {
      return json({ ok: false, error: "Passkey 驗證失敗，請重新嘗試。" }, 401);
    }
    if (!verification.verified) return json({ ok: false, error: "Passkey 驗證未通過。" }, 401);
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("UPDATE passkeys SET counter = ?, last_used_at = ? WHERE credential_id = ?")
      .bind(verification.authenticationInfo.newCounter, now, passkey.credential_id).run();
    const token = await createSession(env.DB);
    return json({ ok: true, verified: true }, 200, { "Set-Cookie": sessionCookie(token) });
  }

  if (request.method === "POST" && path === "/api/logout") {
    const token = getCookie(request, "__Host-chi_auth_session");
    if (token) await env.DB.prepare("DELETE FROM sessions WHERE token_hash = ?").bind(await sha256(token)).run();
    return json({ ok: true }, 200, { "Set-Cookie": sessionCookie("", 0) });
  }

  return json({ ok: false, error: "Not found." }, 404);
}

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (error) {
      console.error("Chi Auth request failed", error?.name || "unknown");
      return json({ ok: false, error: "驗證服務暫時無法處理請求。" }, 500);
    }
  },
};
