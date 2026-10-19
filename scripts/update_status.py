#!/usr/bin/env python3
"""Collect workflow health and project-specific business outcomes for the status dashboard."""
import json
import os
import copy
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from html import unescape
from zoneinfo import ZoneInfo

OWNER = "tsai97216"
EXCLUDED_REPOS = {"chi-brand", "merch-old", "nav-n"}
TOKEN = os.environ.get("GH_TOKEN", "")
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "tsai97216-status-dashboard",
}
if TOKEN:
    HEADERS["Authorization"] = "Bearer " + TOKEN

# The presentation profile is deliberately separate from GitHub's generic run status.
PROFILES = {
    "status": {"kind": "dashboard", "title": "Chi Status 監控儀表板", "description": "儀表板資料更新與部署狀態", "icon": "◈"},
    "vps-01": {"kind": "vps", "title": "VPS-01 · Oracle Cloud", "description": "透過公開服務端點檢查 VPS 對外服務可用性", "icon": "▣"},
    "sc-auto-claim": {"kind": "claim", "title": "荒野亂鬥自動領取", "description": "兩個帳號的實際領取結果與最近成功時間", "icon": "gamepad"},
    "free-game": {"kind": "freegame", "title": "限免遊戲通知", "description": "RSS 掃描、已處理遊戲與文章去重狀態", "icon": "gamepad"},
    "apktwsign": {"kind": "checkin", "title": "APK.TW 自動簽到", "description": "網站回報的簽到結果與最近紀錄", "icon": "✓"},
    "bahasign": {"kind": "checkin", "title": "巴哈姆特自動簽到", "description": "網站回報的簽到結果與最近紀錄", "icon": "✓"},
    "chi-source": {"kind": "source", "title": "Chi Source", "description": "AltStore 來源更新、應用程式版本變動與網站可用性", "icon": "⌘", "health_url": "https://ipa.chi.qzz.io/"},
    "chi-source-personal": {"kind": "source", "title": "Chi Source Personal", "description": "個人來源更新、應用程式版本變動與網站可用性", "icon": "⌘", "health_url": "https://ipap.chi.qzz.io/"},
    "h": {"kind": "deploy", "title": "H", "description": "工具網站部署與實際 HTTP 健康檢查", "icon": "▣", "health_url": "https://h.chi.qzz.io/"},
    "nav": {"kind": "deploy", "title": "Chi 的工具箱", "description": "導航網站部署與實際 HTTP 健康檢查", "icon": "⌖", "health_url": "https://nav.chi.qzz.io/"},
    "merch": {"kind": "deploy", "title": "周邊收藏網", "description": "商品網站部署與實際 HTTP 健康檢查", "icon": "▦", "health_url": "https://merch.chi.qzz.io/"},
    "vaultwarden-service": {"kind": "website", "title": "Vaultwarden", "description": "密碼管理服務存活端點檢查", "icon": "▣", "health_url": "https://vault.chi.qzz.io/alive", "service_name": "Vaultwarden", "health_path": "/alive"},
    "chi-auth-service": {"kind": "website", "title": "Chi Auth", "description": "Passkey／SSO 驗證服務首頁可用性檢查", "icon": "⌑", "health_url": "https://auth.chi.qzz.io/", "service_name": "Chi Auth", "health_path": "/"},
}
RAW_BASE = "https://raw.githubusercontent.com/{}/{}/main/{}"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# Repositories triggered by cron-job.org must fail visibly if dispatches stop.
# Thresholds include generous room for delayed queues and occasional slow runs.
SCHEDULED_RUN_MAX_AGE = {
    "status": 25 * 60,
    "chi-source": 150 * 60,
    "chi-source-personal": 150 * 60,
    "sc-auto-claim": 10 * 60 * 60,
    "free-game": 8 * 60 * 60,
    "apktwsign": 16 * 60 * 60,
    "bahasign": 16 * 60 * 60,
}


def reset_cycle_date(value, reset_hour):
    """Return the service cycle date for a datetime, using Taiwan local time.

    Naive datetimes are interpreted as Taiwan wall-clock time; aware datetimes
    are converted to Asia/Taipei before applying the reset boundary.
    """
    if value.tzinfo is not None:
        value = value.astimezone(TAIPEI_TZ).replace(tzinfo=None)
    return (value - timedelta(hours=reset_hour)).date()

def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)

def get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "tsai97216-status-dashboard"})
    with urllib.request.urlopen(req, timeout=12) as response:
        return response.read().decode("utf-8", errors="replace")

def raw(repo, path):
    try:
        return get_text(RAW_BASE.format(OWNER, repo, path))
    except Exception as exc:
        print(f"Optional business record unavailable: {repo}/{path}: {exc}")
        return None

def parse_json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None

def taipei_time(value):
    if not value:
        return "尚無紀錄"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)



def parse_checkin_record(record):
    """Extract a check-in timestamp and result from supported README formats."""
    if not record:
        return None, None
    timestamp = None
    status_line = None
    status_markers = ("簽到成功", "今日已簽到", "簽到失敗", "執行完成，結果未知")
    for line in record.splitlines():
        if line.lower().startswith("last run:"):
            timestamp = line.split(":", 1)[1].strip()
        if any(marker in line for marker in status_markers):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) >= 3 and re.search(r"\d{4}[-/]\d{2}[-/]\d{2}", cells[-2]):
                timestamp = cells[-2]
                status_line = cells[-1]
            else:
                status_line = re.sub(r"^[|\s#>*-]+", "", line).strip()
            if status_line.startswith("Result:"):
                status_line = status_line.split(":", 1)[1].strip()
            if status_line:
                break
    if not timestamp:
        match = re.search(r"\|[^|]+\|\s*(\d{4}[-/]\d{2}[-/]\d{2}[^|]*)\|", record)
        if match:
            timestamp = match.group(1).strip()
    return timestamp, status_line


def classify_checkin_result(timestamp, status_line, now=None, reset_hour=0, source_available=True):
    """Classify a check-in record against the current Taiwan reset cycle.

    A readable old record is not evidence of today's outcome. Missing or
    unparsable timestamps remain unknown rather than inheriting a prior result.
    """
    if not source_available:
        return {
            "business_status": "unknown",
            "business_label": "來源紀錄讀取失敗，無法確認簽到結果",
            "displayed_result": "監控端無法讀取來源檔，請檢查來源儲存庫或連線",
            "tone": "normal",
        }

    status_line = unescape(status_line or "")
    # Do not treat a positive phrase embedded in an explicit negation as success.
    negated_success = any(marker in status_line for marker in (
        "未簽到成功", "尚未簽到成功", "並未簽到成功",
        "未成功", "尚未成功", "並未成功",
    ))
    has_success_marker = bool(
        status_line
        and not negated_success
        and ("簽到成功" in status_line or "今日已簽到" in status_line)
    )
    has_failure_marker = bool(status_line and "簽到失敗" in status_line)
    conflicting_result = has_success_marker and has_failure_marker
    success = has_success_marker and not has_failure_marker
    failure = has_failure_marker and not has_success_marker
    recorded_at = None
    if timestamp:
        normalized = timestamp.strip().replace("/", "-")
        try:
            recorded_at = datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    recorded_at = datetime.strptime(normalized, fmt)
                    break
                except ValueError:
                    continue

    now_taipei = now or datetime.now(TAIPEI_TZ)
    if now_taipei.tzinfo is not None:
        now_taipei = now_taipei.astimezone(TAIPEI_TZ)
    current_cycle = reset_cycle_date(now_taipei, reset_hour)
    if recorded_at and recorded_at.tzinfo is not None:
        recorded_local = recorded_at.astimezone(TAIPEI_TZ).replace(tzinfo=None)
    else:
        # Source repositories publish Taiwan local wall-clock timestamps.
        recorded_local = recorded_at
    recorded_cycle = reset_cycle_date(recorded_local, reset_hour) if recorded_local else None
    if timestamp and recorded_at is None:
        return {
            "business_status": "unknown",
            "business_label": "時間戳記格式錯誤，無法確認今日結果",
            "displayed_result": "簽到時間無法解析，請檢查來源紀錄格式",
            "tone": "normal",
        }

    now_local = now_taipei.replace(tzinfo=None)
    if recorded_local and recorded_local > now_local:
        return {
            "business_status": "unknown",
            "business_label": "紀錄時間晚於目前時間，無法確認簽到結果",
            "displayed_result": "來源紀錄時間在未來，請檢查來源時區或時間格式",
            "tone": "normal",
        }

    if recorded_cycle != current_cycle:
        return {
            "business_status": "unknown",
            "business_label": "紀錄過期，等待今日更新" if timestamp else "缺少簽到時間，無法確認今日結果",
            "displayed_result": "紀錄過期，尚未確認今日簽到" if timestamp else "缺少時間戳記，無法確認",
            "tone": "normal",
        }

    if conflicting_result:
        return {
            "business_status": "unknown",
            "business_label": "簽到結果文字互相矛盾，無法判讀",
            "displayed_result": "來源紀錄同時包含成功與失敗標記，請檢查原始紀錄",
            "tone": "normal",
        }

    business_status = "success" if success else "failure" if failure else "unknown"
    return {
        "business_status": business_status,
        "business_label": status_line or "紀錄格式無法判讀",
        "displayed_result": status_line or "無法判讀",
        "tone": "good" if success else "bad" if failure else "normal",
    }


def metric(label, value, tone="normal"):
    return {"label": label, "value": str(value) if value is not None else "－", "tone": tone}

def inspect_page_content(status, content_type, body, final_url):
    """Distinguish an HTTP response from a plausible application page."""
    text = body or ""
    lowered = text.lower()
    title_match = re.search(r"<title\b[^>]*>(.*?)</title\s*>", text, re.IGNORECASE | re.DOTALL)
    title = unescape(re.sub(r"\s+", " ", title_match.group(1)).strip())[:120] if title_match else ""
    access_page = (
        "/cdn-cgi/access/login" in (final_url or "").lower()
        or ("cloudflare access" in lowered and
            any(term in lowered for term in ("one-time pin", "login", "email address", "access policy")))
    )
    if access_page:
        return {"ok": None, "protected": True, "title": title, "reason": "Cloudflare Access 登入頁"}
    if not 200 <= status < 400:
        return {"ok": False, "protected": False, "title": title, "reason": f"HTTP {status}"}
    if not text.strip():
        return {"ok": False, "protected": False, "title": title, "reason": "回應內容為空"}
    signals = []
    if "html" in (content_type or "").lower():
        if re.search(r"<script\b", text, re.IGNORECASE):
            signals.append("script")
        if re.search(r"\bid=[^>]*\b(?:app|root|__next|__nuxt|q-app)\b", text, re.IGNORECASE):
            signals.append("app-root")
        if re.search(r"<meta\b[^>]*name=[^>]*viewport", text, re.IGNORECASE):
            signals.append("viewport")
    error_titles = ("404", "not found", "access denied", "bad gateway", "service unavailable",
                    "internal server error", "just a moment", "attention required")
    if title and any(term in title.lower() for term in error_titles):
        return {"ok": False, "protected": False, "title": title, "reason": f"疑似錯誤／挑戰頁：{title}"}
    # Some proxy/server error pages return HTTP 200 and omit <title>; catch
    # recognizable standalone error headings without matching ordinary prose.
    error_body_patterns = (
        r"<h1\b[^>]*>\s*(?:404\s+not found|page not found|bad gateway|service unavailable|gateway timeout|internal server error)\s*</h1\s*>",
        r"<title\b[^>]*>\s*(?:502|503|504)\s*</title\s*>",
        r"<center>\s*nginx\s*</center>",
        r"cloudflare\s+ray\s+id",
    )
    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in error_body_patterns):
        return {"ok": False, "protected": False, "title": title, "reason": "疑似伺服器錯誤頁（HTTP 狀態碼未能反映內容）"}
    if "html" in (content_type or "").lower() and not title:
        # Treat a non-empty HTTP 2xx/3xx response as reachable even when a page omits <title>.
        return {"ok": True, "protected": False, "title": title,
                "reason": "HTTP 回應正常（HTML 無 title，略過標題檢查）", "signals": signals}
    return {"ok": True, "protected": False, "title": title, "reason": "HTTP 與基本頁面內容檢查通過"}


def health_check(url):
    """Check HTTP status plus basic page content; this is not a full end-to-end test."""
    if not url:
        return None
    started = datetime.now(timezone.utc)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tsai97216-status-healthcheck"})
        with urllib.request.urlopen(req, timeout=12) as response:
            status = response.status
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            body = response.read(65536).decode("utf-8", errors="replace")
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        inspected = inspect_page_content(status, content_type, body, final_url)
        return {"ok": inspected["ok"], "reachable": True, "protected": inspected["protected"],
                "status": status, "url": url, "final_url": final_url, "latency_ms": elapsed_ms,
                "content_type": content_type, "title": inspected["title"],
                "content_reason": inspected["reason"], "content_signals": inspected.get("signals", [])}
    except urllib.error.HTTPError as exc:
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {"ok": False, "reachable": True, "protected": False, "status": exc.code, "url": url,
                "final_url": exc.geturl(), "latency_ms": elapsed_ms, "content_reason": f"HTTP {exc.code}"}
    except Exception as exc:
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {"ok": False, "reachable": False, "protected": False, "status": "連線失敗", "url": url,
                "latency_ms": elapsed_ms, "error": str(exc)[:160], "content_reason": "DNS、TLS、逾時或連線錯誤"}

def format_unknown_health_detail(check):
    """Format an inconclusive endpoint check without repeating its status phrase."""
    reason = (check or {}).get("content_reason") or "回應內容不足以確認頁面健康"
    if reason.startswith("HTML 缺少 title，內容狀態未能確認"):
        reason = "HTML 缺少 title"
        signals = (check or {}).get("content_signals") or []
        signal_labels = []
        if "script" in signals:
            signal_labels.append("script")
        if "app-root" in signals:
            signal_labels.append("app/root 容器")
        if "viewport" in signals:
            signal_labels.append("viewport")
        if signal_labels:
            reason += "（頁面包含 " + "、".join(signal_labels) + "）"
    elif reason.startswith("內容狀態未能確認"):
        reason = re.sub(r"^內容狀態未能確認[：:，, ]*", "", reason).strip()
    if not reason:
        reason = "回應內容不足以確認頁面健康"
    status = (check or {}).get("status", "未知")
    return f"狀態未確認 · {reason} · HTTP {status}"


def normalize_run_status(run):
    """Return a conclusion for completed runs, otherwise the live run status."""
    if not isinstance(run, dict):
        return "unknown"
    if run.get("status") == "completed":
        return run.get("conclusion") or "unknown"
    return run.get("status") or "unknown"

def classify_claim_state(state, now=None, reset_hour=16):
    """Classify one Brawl Stars claim record without trusting stale or malformed state."""
    unknown = {"result": "本次執行尚未確認", "tone": "normal"}
    if not isinstance(state, dict):
        return {**unknown, "time": "尚無紀錄"}

    stamp = state.get("lastClaimAt")
    if not stamp:
        return {**unknown, "time": taipei_time(stamp)}

    try:
        claim_dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return {**unknown, "time": taipei_time(stamp)}

    now_taipei = now or datetime.now(TAIPEI_TZ)
    if now_taipei.tzinfo is not None:
        now_taipei = now_taipei.astimezone(TAIPEI_TZ)
    now_local = now_taipei.replace(tzinfo=None)

    if claim_dt.tzinfo is not None:
        claim_local = claim_dt.astimezone(TAIPEI_TZ).replace(tzinfo=None)
    else:
        claim_local = claim_dt

    if claim_local > now_local:
        return {**unknown, "time": taipei_time(stamp)}
    if reset_cycle_date(claim_local, reset_hour) != reset_cycle_date(now_local, reset_hour):
        return {**unknown, "time": taipei_time(stamp)}

    success = state.get("success")
    result_text = state.get("lastResult")
    if success is True and result_text in (None, "", "成功"):
        return {"result": "成功", "tone": "good", "time": taipei_time(stamp)}
    if success is False and result_text in (None, "", "失敗"):
        return {"result": "失敗", "tone": "bad", "time": taipei_time(stamp)}
    return {**unknown, "time": taipei_time(stamp)}


def business_data(repo_name, run):
    profile = PROFILES.get(repo_name, {})
    kind = profile.get("kind", "generic")
    result = {"kind": kind, "title": profile.get("title", repo_name),
              "description": profile.get("description", "最近一次工作流程執行結果"),
              "icon": profile.get("icon", "◉"),
              "business_status": "unknown", "business_label": "尚未建立業務紀錄",
              "metrics": [], "details": [], "note": "", "evidence_url": None}
    if kind == "claim":
        states = []
        taipei_tz = __import__("zoneinfo").ZoneInfo("Asia/Taipei")
        now_taipei = datetime.now(taipei_tz)
        # Brawl Stars daily claim cycle resets at 16:00 Taiwan time.
        current_cycle = reset_cycle_date(now_taipei, 16)
        for account_id, account_label in [("A", "帳號 A"), ("B", "帳號 B")]:
            state = parse_json(raw(repo_name, f"claim_state_{account_id}.json"))
            classified = classify_claim_state(state, now_taipei, 16)
            states.append({"label": account_label, **classified})
        good = sum(1 for s in states if s["result"] == "成功")
        bad = sum(1 for s in states if s["result"] == "失敗")
        current = sum(1 for s in states if s["result"] in ("成功", "失敗"))
        result["business_status"] = "success" if current == len(states) and bad == 0 and good == len(states) else "failure" if bad else "unknown"
        result["business_label"] = (
            f"{good}/{len(states)} 個帳號成功" if current == len(states) and good == len(states)
            else f"{good}/{len(states)} 個帳號成功，{bad} 個失敗" if bad
            else "本輪領取結果待確認"
        )
        result["metrics"] = [metric("本輪成功帳號", f"{good}/{len(states)}", "good" if states and current == len(states) and good == len(states) else "normal"),
                             metric("最近領取", max((s["time"] for s in states), default="尚無紀錄"))]
        result["details"] = states
        result["note"] = "以 claim_state_A/B.json 的實際結果判斷；每日週期於台灣時間 16:00 重置，跨週期的舊結果不沿用。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/tree/main"
    elif kind == "freegame":
        processed = parse_json(raw(repo_name, "data/processed.json"))
        entries = processed if isinstance(processed, list) else []
        total_games = sum(1 for x in entries if str(x).startswith("game|"))
        total_articles = sum(1 for x in entries if str(x).startswith("article|"))
        new_games = 0
        new_articles = 0
        state_commit_time = None
        fresh_state_commit = False
        try:
            commits = get_json(f"https://api.github.com/repos/{OWNER}/{repo_name}/commits?path=data/processed.json&per_page=1")
            if commits:
                latest = commits[0]
                state_commit_time = latest.get("commit", {}).get("committer", {}).get("date") or latest.get("commit", {}).get("author", {}).get("date")
                if state_commit_time and (run or {}).get("created_at"):
                    committed = datetime.fromisoformat(state_commit_time.replace("Z", "+00:00"))
                    started = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                    fresh_state_commit = committed >= started
                if fresh_state_commit:
                    detail = get_json(f"https://api.github.com/repos/{OWNER}/{repo_name}/commits/{latest['sha']}")
                    for changed in detail.get("files", []):
                        if changed.get("filename") != "data/processed.json":
                            continue
                        added = [line[1:].strip().strip('",') for line in (changed.get("patch") or "").splitlines() if line.startswith("+") and not line.startswith("+++")]
                        new_games = sum(1 for line in added if line.startswith("game|"))
                        new_articles = sum(1 for line in added if line.startswith("article|"))
        except Exception as exc:
            print(f"Could not inspect latest processed-state diff: {exc}")
        status = (run or {}).get("status")
        result["business_status"] = "failure" if status == "failure" else "success" if status == "success" and isinstance(processed, list) else "unknown"
        if status == "failure":
            result["business_label"] = "掃描或通知流程失敗"
        elif status == "success" and new_games:
            result["business_label"] = f"本輪成功新增 {new_games} 款遊戲紀錄"
        elif status == "success":
            result["business_label"] = "掃描完成，本輪沒有新增遊戲通知紀錄"
        else:
            result["business_label"] = "掃描結果待確認"
        result["metrics"] = [metric("本輪新增遊戲", new_games, "good" if new_games else "normal"),
                             metric("本輪處理文章", new_articles),
                             metric("累積遊戲／文章", f"{total_games}／{total_articles}")]
        result["details"] = [{"label": "本輪狀態紀錄", "result": "找到本輪狀態提交" if fresh_state_commit else "沒有本輪狀態提交（可能無新項目）", "time": taipei_time(state_commit_time) if state_commit_time else "尚無紀錄", "tone": "good" if fresh_state_commit else "normal"},
                             {"label": "去重狀態檔", "result": "可讀取" if isinstance(processed, list) else "無法讀取", "time": "", "tone": "good" if isinstance(processed, list) else "bad"}]
        result["note"] = "本輪新增數以 data/processed.json 最近一次提交的實際 diff 計算；遊戲紀錄只有在通知送出後才會加入。若本輪沒有狀態提交，顯示 0，而不把累積數誤當成本輪成果。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/commits/main/data/processed.json"
    elif kind == "checkin":
        record = raw(repo_name, "activity.md") if repo_name == "apktwsign" else raw(repo_name, "README.md")
        timestamp, status_line = parse_checkin_record(record)
        classification = classify_checkin_result(timestamp, status_line, reset_hour=0, source_available=record is not None)
        business_status = classification["business_status"]
        business_label = classification["business_label"]
        displayed_result = classification["displayed_result"]
        tone = classification["tone"]
        result["business_status"] = business_status
        result["business_label"] = business_label
        result["metrics"] = [metric("業務狀態", "成功" if business_status == "success" else "失敗" if business_status == "failure" else "待確認", tone),
                             metric("最近簽到", timestamp or "尚無紀錄")]
        result["details"] = [{"label": "來源紀錄", "result": displayed_result, "time": timestamp or "尚無紀錄", "tone": tone}]
        result["note"] = "簽到結果只在台灣當日有效；跨日後若來源檔仍是昨天或缺少可辨識時間，會標示待確認，不沿用舊結果。"
        evidence_file = "activity.md" if repo_name == "apktwsign" else "README.md"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/blob/main/{evidence_file}"
    elif kind == "dashboard":
        status = (run or {}).get("status")
        result["business_status"] = "running" if status in ("in_progress", "queued", "waiting", "requested") else "success" if status == "success" else "failure" if status == "failure" else "unknown"
        result["business_label"] = "儀表板正在更新" if result["business_status"] == "running" else "資料更新成功" if result["business_status"] == "success" else "資料更新失敗" if result["business_status"] == "failure" else "等待資料更新"
        result["metrics"] = [metric("監控範圍", "公開儲存庫"), metric("更新頻率", "每 10 分鐘自動更新"), metric("資料更新狀態", result["business_label"], "good" if result["business_status"] == "success" else "bad" if result["business_status"] == "failure" else "normal")]
        result["details"] = [{"label": "最近更新工作流程", "result": result["business_label"], "time": taipei_time((run or {}).get("updated_at")), "tone": "good" if result["business_status"] == "success" else "bad" if result["business_status"] == "failure" else "normal"}]
        result["note"] = "此專案負責收集各公開儲存庫的工作流程與業務狀態，自己的執行狀態會在更新期間短暫顯示為進行中。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/actions"
    elif kind == "vps":
        # VPS-01 is considered operational when at least two of its three
        # public endpoints return HTTP 200. This is an HTTP-level threshold.
        services = [
            ("Alist", "https://alist.chi.qzz.io/"),
            ("BiliTool", "https://bili.chi.qzz.io/"),
            ("Twitch Drops Miner", "https://twitch.chi.qzz.io/"),
        ]
        checks = []
        for label, url in services:
            check = health_check(url)
            checks.append({"label": label, "url": url, "check": check})
        def endpoint_http_200(check):
            return bool(check and check.get("status") == 200)
        healthy = sum(1 for item in checks if endpoint_http_200(item["check"]))
        failed = sum(1 for item in checks if item["check"] and item["check"].get("status") not in (None, 200))
        unknown = sum(1 for item in checks if not item["check"] or item["check"].get("status") is None)
        total = len(checks)
        threshold = 2
        if healthy >= threshold:
            result["business_status"] = "success"
            result["business_label"] = f"VPS-01 正常運作（至少 {threshold}/{total} 個端點 HTTP 200）"
        elif failed:
            result["business_status"] = "failure"
            result["business_label"] = f"VPS-01 異常（{healthy}/{total} 個端點 HTTP 200）"
        else:
            result["business_status"] = "unknown"
            result["business_label"] = f"VPS-01 狀態未確認（{healthy}/{total} 個端點 HTTP 200）"
        result["metrics"] = [
            metric("HTTP 200 端點", f"{healthy}/{total}", "good" if healthy >= threshold else "bad" if failed else "normal"),
            metric("非 200 端點", failed, "bad" if failed else "good"),
            metric("未取得狀態", unknown, "normal" if unknown else "good"),
        ]
        for item in checks:
            check = item["check"]
            if not check:
                detail_result, tone = "未取得檢查結果", "normal"
            elif check.get("status") == 200 and check.get("protected"):
                detail_result, tone = "Cloudflare Access 登入頁可達 · HTTP 200", "good"
            elif check.get("status") == 200:
                detail_result, tone = f"HTTP 200 · {check.get('content_reason') or '端點有回應'}", "good"
            elif check.get("status") is not None:
                detail_result, tone = f"非 HTTP 200 · HTTP {check.get('status')}", "bad"
            else:
                detail_result, tone = format_unknown_health_detail(check), "normal"
            if check and check.get("latency_ms") is not None:
                detail_result += f" · {check['latency_ms']} ms"
            result["details"].append({
                "label": item["label"],
                "result": detail_result,
                "time": "",
                "tone": tone,
            })
        result["note"] = "判定標準：Alist、BiliTool、Twitch Drops Miner 三個公開端點中，至少兩個回傳 HTTP 200，即判定服務正常。"
        result["evidence_url"] = None
    elif kind == "website":
        health = health_check(profile.get("health_url"))
        service_name = profile.get("service_name") or profile.get("title") or repo_name
        health_path = profile.get("health_path") or "/"
        if health and health.get("ok") is True:
            result["business_status"] = "success"
            result["business_label"] = "Vaultwarden 存活檢查通過" if repo_name == "vaultwarden-service" else f"{service_name} 端點檢查通過"
        elif health and health.get("ok") is False:
            result["business_status"] = "failure"
            result["business_label"] = f"{service_name} 端點異常"
        else:
            result["business_status"] = "unknown"
            result["business_label"] = f"{service_name} 狀態未確認"
        result["metrics"] = [
            metric("檢查端點", health_path),
            metric("HTTP 狀態", str(health.get("status")) if health and health.get("status") is not None else "未取得",
                   "good" if health and health.get("ok") is True else "bad" if health and health.get("ok") is False else "normal"),
            metric("回應時間", f'{health.get("latency_ms")} ms' if health and health.get("latency_ms") is not None else "未取得"),
        ]
        if health:
            result["details"] = [
                {"label": "端點檢查", "result": health.get("content_reason") or "未取得內容判讀",
                 "time": f'HTTP {health.get("status", "未知")}', "tone": "good" if health.get("ok") is True else "bad" if health.get("ok") is False else "normal"},
            ]
        if repo_name == "vaultwarden-service":
            result["note"] = "使用 Vaultwarden 的公開 /alive 存活端點，每 10 分鐘自動更新檢查 HTTP 與非空回應。這只確認服務端點可回應，不代表資料庫、登入或同步等所有功能都已完整驗證。"
        else:
            result["note"] = f"每 10 分鐘自動更新檢查 {service_name} 的公開首頁（HTTP 狀態、回應內容與回應時間）。這是基本可用性探測，不代表 Passkey、SSO 或所有驗證流程均已完成端對端驗證。"
        result["evidence_url"] = profile.get("health_url")
    elif kind == "source":
        readme = raw(repo_name, "README.md") or ""
        auto_match = re.search(r"最近自動檢查：\*\*\s*([^（\n]+)", readme)
        content_match = re.search(r"最近內容更新：\*\*\s*([^（\n]+)", readme)
        rows = []
        for line in readme.splitlines():
            if not line.startswith("|") or ("Updated" not in line and "Unchanged" not in line):
                continue
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) < 4:
                continue
            name_match = re.search(r"\[([^\]]+)\]", cells[0])
            if name_match:
                rows.append((name_match.group(1), "Updated" if "Updated" in cells[2] else "Unchanged"))
        updated_names = [name for name, state in rows if state == "Updated"]
        unchanged_count = sum(1 for _, state in rows if state == "Unchanged")
        health = health_check(profile.get("health_url"))
        result["business_status"] = "failure" if health and health.get("ok") is False else "success" if health and health.get("ok") is True else "unknown"
        result["business_label"] = "來源網站內容檢查通過" if health and health.get("ok") is True else "來源網站回應異常" if health and health.get("ok") is False else "網站狀態未知（可能受 Access 保護）"
        result["metrics"] = [metric("應用程式數量", len(rows)), metric("本次偵測到的更新", len(updated_names), "good" if updated_names else "normal"),
                             metric("網站 HTTP", str(health["status"]) if health else "未檢查", "good" if health and health.get("ok") is True else "bad" if health and health.get("ok") is False else "normal"),
                             metric("頁面內容", "通過" if health and health.get("ok") is True else "異常" if health and health.get("ok") is False else "未確認", "good" if health and health.get("ok") is True else "bad" if health and health.get("ok") is False else "normal")]
        result["details"] = [{"label": "自動檢查", "result": auto_match.group(1).strip() if auto_match else "README 未提供紀錄", "time": "", "tone": "normal"},
                             {"label": "內容更新", "result": content_match.group(1).strip() if content_match else "README 未提供紀錄", "time": "", "tone": "normal"},
                             {"label": "版本狀態", "result": f"{len(updated_names)} 個應用程式更新、{unchanged_count} 個未變更", "time": "", "tone": "good" if updated_names else "normal"}]
        if updated_names:
            result["details"].append({"label": "已更新的應用程式", "result": "、".join(updated_names[:8]), "time": "", "tone": "good"})
        result["note"] = "應用程式更新數來自來源儲存庫的 README 狀態表；網站可用性來自即時 HTTP 檢查。版本表是來源專案最後一次自動檢查的紀錄，不代表每個應用程式都能成功安裝。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/blob/main/README.md"
    elif kind == "deploy":
        status = (run or {}).get("status")
        health = health_check(profile.get("health_url"))
        workflow_ok = status == "success"
        if health and health.get("ok") is False:
            result["business_status"] = "failure"
            result["business_label"] = "網站 HTTP 或頁面內容檢查失敗"
        elif health and health.get("ok") is True and workflow_ok:
            result["business_status"] = "success"
            result["business_label"] = "部署成功、HTTP 與基本頁面內容檢查通過"
        elif health and health.get("protected") and workflow_ok:
            result["business_status"] = "unknown"
            result["business_label"] = "部署成功，但網站受 Access 保護，無法確認頁面內容"
        elif status == "failure":
            result["business_status"] = "failure"
            result["business_label"] = "最近一次部署失敗"
        elif status in ("in_progress", "queued", "waiting", "requested"):
            result["business_status"] = "running"
            result["business_label"] = "部署進行中"
        elif workflow_ok:
            result["business_status"] = "success"
            result["business_label"] = "最近一次部署成功"
        else:
            result["business_status"] = "unknown"
            result["business_label"] = "部署狀態未知"
        result["metrics"] = [metric("部署結果", "成功" if workflow_ok else status or "未知", "good" if workflow_ok else "bad" if status == "failure" else "normal"),
                             metric("分支", (run or {}).get("head_branch") or "－"),
                             metric("網站 HTTP", str(health["status"]) if health else "未設定", "good" if health and health.get("ok") is True else "bad" if health and health.get("ok") is False else "normal"),
                             metric("頁面內容", "通過" if health and health.get("ok") is True else "異常" if health and health.get("ok") is False else "未確認", "good" if health and health.get("ok") is True else "bad" if health and health.get("ok") is False else "normal")]
        result["details"] = [{"label": "最近一次部署", "result": result["business_label"], "time": taipei_time((run or {}).get("updated_at")), "tone": "good" if result["business_status"] == "success" else "bad" if result["business_status"] == "failure" else "normal"}]
        if health:
            result["details"].append({"label": "網站可用性檢查", "result": f"{health['url']} · HTTP {health['status']}", "time": "", "tone": "good" if health.get("ok") is True else "bad" if health.get("ok") is False else "normal"})
            result["details"].append({"label": "頁面內容", "result": health.get("content_reason") or "未取得內容判讀", "time": health.get("title") or "", "tone": "good" if health.get("ok") is True else "bad" if health.get("ok") is False else "normal"})
        result["note"] = "綜合 GitHub Actions 部署結果與即時 HTTP 探測。HTTP 200 代表網站有回應，不代表站內所有功能均正常。" if profile.get("health_url") else "目前僅依 GitHub Actions 判定部署流程；此儲存庫尚未設定可驗證的正式網址。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/actions"
    else:
        status = normalize_run_status(run)
        result["business_status"] = status
        result["business_label"] = "最近工作流程：" + str(status or "尚無紀錄")
        result["metrics"] = [metric("Workflow", (run or {}).get("name") or "尚無紀錄"),
                             metric("分支", (run or {}).get("head_branch") or "－")]
        result["details"] = []
        result["note"] = "尚未設定專屬的業務資料解析規則。"
    return result

def apply_schedule_freshness(item, now=None):
    """Mark scheduled repositories unhealthy when no recent dispatch/run is visible."""
    max_age = SCHEDULED_RUN_MAX_AGE.get(item.get("name"))
    if max_age is None:
        return item

    stamp = item.get("created_at")
    try:
        started = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        item["status"] = "unknown"
        item["monitor_warning"] = "排程執行時間缺失或格式無效"
        business = item.get("business") or {}
        business["business_status"] = "unknown"
        business["business_label"] = "無法確認排程是否準時執行"
        business["note"] = (business.get("note", "") + "\n監控端無法解析最近一次 Workflow 的開始時間，因此無法確認排程新鮮度。").strip()
        item["business"] = business
        return item

    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    age_seconds = max(0, int((now_utc.astimezone(timezone.utc) - started.astimezone(timezone.utc)).total_seconds()))
    item["schedule_age_seconds"] = age_seconds
    item["schedule_max_age_seconds"] = max_age
    if age_seconds <= max_age:
        return item

    age_hours = age_seconds / 3600
    limit_hours = max_age / 3600
    age_label = f"{age_hours:.1f} 小時" if age_hours >= 1 else f"{age_seconds // 60} 分鐘"
    limit_label = f"{limit_hours:g} 小時" if limit_hours >= 1 else f"{max_age // 60} 分鐘"
    item["status"] = "failure"
    item["monitor_warning"] = f"最近一次排程執行距今 {age_label}，超過 {limit_label} 門檻"
    business = item.get("business") or {}
    business["business_status"] = "failure"
    business["business_label"] = "排程執行逾期，可能未收到新的觸發"
    business["note"] = (business.get("note", "") + f"\n排程新鮮度監控：{item['monitor_warning']}。").strip()
    business["metrics"] = list(business.get("metrics") or [])
    business["metrics"].append(metric("排程新鮮度", age_label, "bad"))
    item["business"] = business
    return item


def stale_fallback(repo, previous_item, error):
    """Keep a card visible when one repository's status API call temporarily fails."""
    if not previous_item:
        return None
    item = copy.deepcopy(previous_item)
    item["status"] = "unknown"
    item["updated_at"] = datetime.now(timezone.utc).isoformat()
    item["event"] = "monitor-error"
    item["monitor_warning"] = str(error)[:180]
    business = item.get("business") or {}
    previous_label = business.get("business_label") or "上次資料"
    business["business_status"] = "unknown"
    business["business_label"] = "暫時無法更新，保留上次資料"
    business["note"] = (business.get("note", "") + f"\n本輪無法取得最新狀態（{previous_label}）；目前展示的是上次資料，請勿視為即時結果。").strip()
    business["metrics"] = list(business.get("metrics") or [])
    business["metrics"].append(metric("資料更新狀態", "暫時無法更新", "normal"))
    item["business"] = business
    return item

def main():
    previous_payload = parse_json(open("status.json", encoding="utf-8").read()) if os.path.exists("status.json") else {}
    previous_items = (previous_payload or {}).get("repositories", [])
    previous_by_name = {
        item.get("name"): item for item in previous_items
        if isinstance(item, dict) and item.get("name")
    }
    repos = []
    for page in range(1, 4):
        batch = get_json(f"https://api.github.com/users/{OWNER}/repos?type=public&per_page=100&page={page}&sort=updated")
        repos.extend(r for r in batch if not r.get("fork", False) and not r.get("archived", False))
        if len(batch) < 100:
            break
    results = []
    for repo in repos:
        if repo["name"] in EXCLUDED_REPOS:
            continue
        full_name = repo["full_name"]
        try:
            data = get_json(f"https://api.github.com/repos/{full_name}/actions/runs?per_page=10")
            runs = data.get("workflow_runs", [])
            if repo["name"] == "status":
                # The collector sees its own current run as in_progress. Use the latest
                # completed run for its card so the published snapshot does not stay running.
                completed_runs = [
                    candidate for candidate in runs
                    if candidate.get("status") == "completed"
                    and candidate.get("conclusion") not in ("cancelled", "skipped")
                ]
                if completed_runs:
                    # Cancelled maintenance/push runs are not meaningful health results.
                    # Keep real failures visible, but avoid letting a cancelled run mask
                    # the latest completed success or failure.
                    runs = completed_runs
            if not runs:
                fallback = stale_fallback(repo, previous_by_name.get(repo["name"]), "此儲存庫尚無工作流程執行紀錄")
                if fallback:
                    results.append(fallback)
                continue
            run = runs[0]
            duration = None
            if run.get("run_started_at") and run.get("status") == "completed":
                start = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                duration = max(0, int((end - start).total_seconds()))
            status = normalize_run_status(run)
            item = {
                "name": repo["name"], "full_name": full_name, "html_url": repo["html_url"],
                "workflow": run.get("name") or run.get("display_title") or "GitHub Actions",
                "status": status, "branch": run.get("head_branch") or repo.get("default_branch"),
                "updated_at": run.get("updated_at") or run.get("created_at"),
                "created_at": run.get("created_at"),
                "event": run.get("event"),
                "commit_message": ((run.get("head_commit") or {}).get("message") or "").splitlines()[0][:180],
                "duration_seconds": duration, "runs_url": repo["html_url"] + "/actions",
                "run_url": run.get("html_url"),
            }
            item["business"] = business_data(repo["name"], item)
            item = apply_schedule_freshness(item)
            results.append(item)
        except urllib.error.HTTPError as exc:
            print(f"Status API error for {full_name}: HTTP {exc.code}")
            fallback = stale_fallback(repo, previous_by_name.get(repo["name"]), f"HTTP {exc.code}")
            if fallback:
                results.append(fallback)
        except Exception as exc:
            print(f"Status API error for {full_name}: {exc}")
            fallback = stale_fallback(repo, previous_by_name.get(repo["name"]), str(exc))
            if fallback:
                results.append(fallback)
    # Synthetic host monitor: not a GitHub repository, but rendered alongside repo cards.
    host_item = {
        "name": "vps-01", "full_name": "VPS-01 · Oracle Cloud Infrastructure",
        "html_url": "https://alist.chi.qzz.io/",
        "workflow": "外部服務探測", "status": "unknown", "branch": "OCI",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event": "healthcheck", "commit_message": "每 10 分鐘自動更新檢查三個公開服務端點",
        "duration_seconds": None,
        "runs_url": f"https://github.com/{OWNER}/status/actions",
        "run_url": f"https://github.com/{OWNER}/status/actions",
    }
    host_item["business"] = business_data("vps-01", host_item)
    host_item["status"] = ("success" if host_item["business"]["business_status"] == "success"
                           else "failure" if host_item["business"]["business_status"] == "failure"
                           else "unknown")
    results.append(host_item)
    # Vaultwarden is a service endpoint, not necessarily a repository with its own Workflow.
    vault_item = {
        "name": "vaultwarden-service", "full_name": "Vaultwarden · 密碼管理服務",
        "html_url": "https://vault.chi.qzz.io/",
        "workflow": "外部服務探測", "status": "unknown", "branch": "VPS-01",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event": "healthcheck", "commit_message": "每 10 分鐘自動更新檢查 Vaultwarden /alive 存活端點",
        "duration_seconds": None,
        "runs_url": f"https://github.com/{OWNER}/status/actions",
        "run_url": f"https://github.com/{OWNER}/status/actions",
    }
    vault_item["business"] = business_data("vaultwarden-service", vault_item)
    vault_item["status"] = ("success" if vault_item["business"]["business_status"] == "success"
                            else "failure" if vault_item["business"]["business_status"] == "failure"
                            else "unknown")
    results.append(vault_item)
    # Chi Auth is an external authentication endpoint, not necessarily a GitHub Workflow.
    auth_item = {
        "name": "chi-auth-service", "full_name": "Chi Auth · Passkey／SSO 驗證服務",
        "html_url": "https://auth.chi.qzz.io/",
        "workflow": "外部服務探測", "status": "unknown", "branch": "VPS-01",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event": "healthcheck", "commit_message": "每 10 分鐘自動更新檢查 Chi Auth 公開首頁",
        "duration_seconds": None,
        "runs_url": f"https://github.com/{OWNER}/status/actions",
        "run_url": f"https://github.com/{OWNER}/status/actions",
    }
    auth_item["business"] = business_data("chi-auth-service", auth_item)
    auth_item["status"] = ("success" if auth_item["business"]["business_status"] == "success"
                           else "failure" if auth_item["business"]["business_status"] == "failure"
                           else "unknown")
    results.append(auth_item)
    def dashboard_priority(item):
        business_status = (item.get("business") or {}).get("business_status")
        workflow_status = item.get("status")
        if (item.get("business") or {}).get("kind") == "vps" and (
            business_status == "failure" or workflow_status in ("failure", "timed_out", "action_required")
        ):
            return -1
        if business_status == "failure" or workflow_status in ("failure", "timed_out", "action_required"):
            return 0
        if business_status == "running" or workflow_status in ("in_progress", "queued", "requested", "waiting"):
            return 1
        if business_status == "unknown" or workflow_status in (None, "unknown"):
            return 2
        return 3

    # Keep priority groups stable while sorting recent activity first inside each group.
    results.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    results.sort(key=dashboard_priority)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(),
               "repository_count": len(results), "repositories": results}
    with open("status.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Collected workflow and project-specific business status for {len(results)} repositories.")

if __name__ == "__main__":
    main()
