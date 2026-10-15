#!/usr/bin/env python3
"""Collect workflow health and project-specific business outcomes for the status dashboard."""
import json
import os
import copy
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from html import unescape

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
    "status": {"kind": "dashboard", "title": "監控中心", "description": "儀表板自身的資料更新與部署", "icon": "◈"},
    "vps-01": {"kind": "vps", "title": "VPS-01 · Oracle Cloud", "description": "透過公開服務端點檢查 VPS 對外可用性", "icon": "▣"},
    "sc-auto-claim": {"kind": "claim", "title": "荒野亂鬥自動領取", "description": "兩個帳號的實際領取結果與最近成功時間", "icon": "gamepad"},
    "free-game": {"kind": "freegame", "title": "免費遊戲通知", "description": "RSS 掃描、已處理遊戲與文章去重狀態", "icon": "gamepad"},
    "apktwsign": {"kind": "checkin", "title": "APK.TW 自動簽到", "description": "網站回報的簽到結果與最近紀錄", "icon": "✓"},
    "bahasign": {"kind": "checkin", "title": "巴哈姆特自動簽到", "description": "網站回報的簽到結果與最近紀錄", "icon": "✓"},
    "chi-source": {"kind": "source", "title": "Chi Source", "description": "AltStore 來源更新、App 版本變動與網站可用性", "icon": "⌘", "health_url": "https://ipa.chi.qzz.io/"},
    "chi-source-personal": {"kind": "source", "title": "Chi Source Personal", "description": "個人來源更新、App 版本變動與網站可用性", "icon": "⌘", "health_url": "https://ipap.chi.qzz.io/"},
    "h": {"kind": "deploy", "title": "H 連結工具", "description": "工具網站部署與實際 HTTP 健康檢查", "icon": "↗", "health_url": "https://h.chi.qzz.io/"},
    "nav": {"kind": "deploy", "title": "Chi 導航站", "description": "導航網站部署與實際 HTTP 健康檢查", "icon": "⌖", "health_url": "https://nav.chi.qzz.io/"},
    "merch": {"kind": "deploy", "title": "Merch 商品資料", "description": "商品網站部署與實際 HTTP 健康檢查", "icon": "▦", "health_url": "https://merch.chi.qzz.io/"},
}
RAW_BASE = "https://raw.githubusercontent.com/{}/{}/main/{}"

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
        return dt.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)

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
    if "html" in (content_type or "").lower() and not title:
        return {"ok": False, "protected": False, "title": title, "reason": "HTML 缺少 title，可能是錯誤頁或不完整回應"}
    error_titles = ("404", "not found", "access denied", "bad gateway", "service unavailable",
                    "internal server error", "just a moment", "attention required")
    if title and any(term in title.lower() for term in error_titles):
        return {"ok": False, "protected": False, "title": title, "reason": f"疑似錯誤／挑戰頁：{title}"}
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
                "content_reason": inspected["reason"]}
    except urllib.error.HTTPError as exc:
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {"ok": False, "reachable": True, "protected": False, "status": exc.code, "url": url,
                "final_url": exc.geturl(), "latency_ms": elapsed_ms, "content_reason": f"HTTP {exc.code}"}
    except Exception as exc:
        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {"ok": False, "reachable": False, "protected": False, "status": "連線失敗", "url": url,
                "latency_ms": elapsed_ms, "error": str(exc)[:160], "content_reason": "DNS、TLS、逾時或連線錯誤"}

def normalize_run_status(run):
    """Return a conclusion for completed runs, otherwise the live run status."""
    if not isinstance(run, dict):
        return "unknown"
    if run.get("status") == "completed":
        return run.get("conclusion") or "unknown"
    return run.get("status") or "unknown"

def business_data(repo_name, run):
    profile = PROFILES.get(repo_name, {})
    kind = profile.get("kind", "generic")
    result = {"kind": kind, "title": profile.get("title", repo_name),
              "description": profile.get("description", "最近一次 Workflow 執行狀況"),
              "icon": profile.get("icon", "◉"),
              "business_status": "unknown", "business_label": "尚未建立業務紀錄",
              "metrics": [], "details": [], "note": "", "evidence_url": None}
    if kind == "claim":
        states = []
        for account_id, account_label in [("A", "帳號 A"), ("B", "帳號 B")]:
            state = parse_json(raw(repo_name, f"claim_state_{account_id}.json"))
            if state:
                success = state.get("success")
                result_text = state.get("lastResult") or ("成功" if success is True else "失敗" if success is False else "未知")
                tone = "good" if result_text == "成功" else "bad" if result_text == "失敗" else "normal"
                states.append({"label": account_label, "result": result_text, "time": taipei_time(state.get("lastClaimAt")), "tone": tone})
        good = sum(s["result"] == "成功" for s in states)
        bad = sum(s["result"] == "失敗" for s in states)
        result["business_status"] = "success" if states and bad == 0 and good == len(states) else "failure" if bad else "unknown"
        result["business_label"] = f"{good}/{len(states)} 個帳號成功" if states else "找不到帳號狀態檔"
        result["metrics"] = [metric("成功帳號", f"{good}/{len(states)}", "good" if states and good == len(states) else "bad"),
                             metric("最近領取", max((s["time"] for s in states), default="尚無紀錄"))]
        result["details"] = states
        result["note"] = "以 claim_state_A/B.json 的實際結果判斷，不以 Actions 綠勾代替領取成功。"
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
        timestamp, status_line = None, None
        if record:
            for line in record.splitlines():
                if line.lower().startswith("last run:"):
                    timestamp = line.split(":", 1)[1].strip()
                if "簽到成功" in line or "今日已簽到" in line or "簽到失敗" in line or "執行完成，結果未知" in line:
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
                m = re.search(r"\|[^|]+\|\s*(\d{4}[-/]\d{2}[-/]\d{2}[^|]*)\|", record)
                if m:
                    timestamp = m.group(1).strip()
        status_line = unescape(status_line or "")
        success = bool(status_line and ("簽到成功" in status_line or "今日已簽到" in status_line))
        failure = bool(status_line and "簽到失敗" in status_line)
        result["business_status"] = "success" if success else "failure" if failure else "unknown"
        result["business_label"] = status_line or "紀錄格式無法判讀"
        result["metrics"] = [metric("業務結果", "成功" if success else "失敗" if failure else "未知", "good" if success else "bad" if failure else "normal"),
                             metric("最近簽到", timestamp or "尚無紀錄")]
        result["details"] = [{"label": "來源紀錄", "result": status_line or "無法判讀", "time": timestamp or "尚無紀錄", "tone": "good" if success else "bad" if failure else "normal"}]
        result["note"] = "讀取專案自己更新的簽到紀錄；如果腳本只回報文字或格式改變，會標示未知而不是猜測成功。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/blob/main/README.md"
    elif kind == "dashboard":
        status = (run or {}).get("status")
        result["business_status"] = "running" if status in ("in_progress", "queued", "waiting", "requested") else "success" if status == "success" else "failure" if status == "failure" else "unknown"
        result["business_label"] = "儀表板正在更新" if result["business_status"] == "running" else "資料更新成功" if result["business_status"] == "success" else "資料更新失敗" if result["business_status"] == "failure" else "等待資料更新"
        result["metrics"] = [metric("監控範圍", "公開 Repo"), metric("更新頻率", "每 10 分鐘"), metric("資料狀態", result["business_label"], "good" if result["business_status"] == "success" else "bad" if result["business_status"] == "failure" else "normal")]
        result["details"] = [{"label": "最近更新流程", "result": result["business_label"], "time": taipei_time((run or {}).get("updated_at")), "tone": "good" if result["business_status"] == "success" else "bad" if result["business_status"] == "failure" else "normal"}]
        result["note"] = "此專案負責收集各 Repo 的 Workflow 與業務結果，自己的執行狀態會在更新期間短暫顯示為進行中。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/actions"
    elif kind == "vps":
        # All three VPS-01 endpoints must pass. Twitch's Cloudflare Access
        # login page is an expected successful response for this endpoint.
        services = [
            ("Alist", "https://alist.chi.qzz.io/"),
            ("BiliTool", "https://bili.chi.qzz.io/"),
            ("Twitch Drops Miner", "https://twitch.chi.qzz.io/"),
        ]
        checks = []
        for label, url in services:
            check = health_check(url)
            checks.append({"label": label, "url": url, "check": check})
        def endpoint_ok(check):
            return bool(check and (check.get("ok") is True or check.get("protected") is True))
        healthy = sum(1 for item in checks if endpoint_ok(item["check"]))
        failed = sum(1 for item in checks if item["check"] and item["check"].get("ok") is False)
        unknown = sum(1 for item in checks if not item["check"] or (item["check"].get("ok") is None and not item["check"].get("protected")))
        total = len(checks)
        if healthy == total:
            result["business_status"] = "success"
            result["business_label"] = f"VPS-01 對外端點正常（3/3 HTTP 回應；不代表 VM/SSH 健康）"
        elif failed:
            result["business_status"] = "failure"
            result["business_label"] = f"VPS-01 異常（{healthy}/{total} 成功／{failed} 異常／{unknown} 未知）"
        else:
            result["business_status"] = "unknown"
            result["business_label"] = f"VPS-01 狀態未能完全確認（{healthy}/{total} 成功／{unknown} 未知）"
        result["metrics"] = [
            metric("成功端點", f"{healthy}/{total}", "good" if healthy == total else "bad" if failed else "normal"),
            metric("異常端點", failed, "bad" if failed else "good"),
            metric("未確認端點", unknown, "normal" if unknown else "good"),
        ]
        for item in checks:
            check = item["check"]
            if not check:
                detail_result, tone = "未取得檢查結果", "normal"
            elif check.get("protected"):
                detail_result, tone = f"Cloudflare Access 登入頁可達 · HTTP {check['status']}（僅確認 Access 回應）", "good"
            elif check.get("ok") is True:
                detail_result, tone = f"公開端點有 HTTP 回應 · HTTP {check['status']}（未驗證站內功能）", "good"
            else:
                detail_result, tone = f"端點異常 · HTTP {check.get('status', '未知')}", "bad" if check.get("ok") is False else "normal"
            if check and check.get("latency_ms") is not None:
                detail_result += f" · {check['latency_ms']} ms"
            result["details"].append({
                "label": item["label"],
                "result": detail_result,
                "time": "",
                "tone": tone,
            })
        result["note"] = "此卡只驗證 Alist、BiliTool、Twitch Drops Miner 三個公開網址是否有 HTTP 回應，不等同於確認應用程式內部功能或 VPS 本身健康。Twitch Drops Miner 若回應預期的 Cloudflare Access 登入頁，只代表 Access 閘道有回應，不代表登入後的後端服務可用。任一端點明確異常即判定對外服務異常；此探測無法確認 VM、SSH、CPU、記憶體或磁碟狀態。"
        result["evidence_url"] = None
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
        result["metrics"] = [metric("App 數量", len(rows)), metric("本次標示更新", len(updated_names), "good" if updated_names else "normal"),
                             metric("網站 HTTP", str(health["status"]) if health else "未檢查", "good" if health and health["ok"] else "bad" if health else "normal")]
        result["details"] = [{"label": "自動檢查", "result": auto_match.group(1).strip() if auto_match else "README 無紀錄", "time": "", "tone": "normal"},
                             {"label": "內容更新", "result": content_match.group(1).strip() if content_match else "README 無紀錄", "time": "", "tone": "normal"},
                             {"label": "版本狀態", "result": f"{len(updated_names)} 個 App 更新、{unchanged_count} 個未變更", "time": "", "tone": "good" if updated_names else "normal"}]
        if updated_names:
            result["details"].append({"label": "更新的 App", "result": "、".join(updated_names[:8]), "time": "", "tone": "good"})
        result["note"] = "App 更新數來自來源 Repo 的 README 狀態表；網站可用性來自即時 HTTP 檢查。版本表是來源專案最後一次自動檢查的紀錄，不代表每個 App 都可安裝成功。"
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
            result["business_label"] = "最近部署失敗"
        elif status in ("in_progress", "queued", "waiting", "requested"):
            result["business_status"] = "running"
            result["business_label"] = "部署進行中"
        elif workflow_ok:
            result["business_status"] = "success"
            result["business_label"] = "最近部署成功"
        else:
            result["business_status"] = "unknown"
            result["business_label"] = "部署狀態未知"
        result["metrics"] = [metric("部署結果", "成功" if workflow_ok else status or "未知", "good" if workflow_ok else "bad" if status == "failure" else "normal"),
                             metric("分支", (run or {}).get("head_branch") or "－"),
                             metric("網站 HTTP", str(health["status"]) if health else "未設定", "good" if health and health["ok"] else "bad" if health else "normal")]
        result["details"] = [{"label": "最近部署", "result": result["business_label"], "time": taipei_time((run or {}).get("updated_at")), "tone": "good" if result["business_status"] == "success" else "bad" if result["business_status"] == "failure" else "normal"}]
        if health:
            result["details"].append({"label": "網站檢查", "result": f"{health['url']} · HTTP {health['status']}", "time": "", "tone": "good" if health["ok"] else "bad"})
        result["note"] = "結合 GitHub Actions 部署結果與即時 HTTP 健康檢查；HTTP 200 代表網站有回應，不保證站內每項功能皆正常。" if profile.get("health_url") else "目前僅依 GitHub Actions 判定部署流程；此舊版或文件型 Repo 尚未設定可驗證的正式網址。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/actions"
    else:
        status = normalize_run_status(run)
        result["business_status"] = status
        result["business_label"] = "最近 Workflow：" + str(status or "尚無紀錄")
        result["metrics"] = [metric("Workflow", (run or {}).get("name") or "尚無紀錄"),
                             metric("分支", (run or {}).get("head_branch") or "－")]
        result["details"] = []
        result["note"] = "尚未配置專屬業務資料解析器。"
    return result

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
    business["metrics"].append(metric("資料狀態", "暫時無法更新", "normal"))
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
            data = get_json(f"https://api.github.com/repos/{full_name}/actions/runs?per_page=1")
            runs = data.get("workflow_runs", [])
            if not runs:
                fallback = stale_fallback(repo, previous_by_name.get(repo["name"]), "此 Repo 尚無 Workflow 執行紀錄")
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
        "event": "healthcheck", "commit_message": "每 10 分鐘檢查三個公開服務端點",
        "duration_seconds": None,
        "runs_url": f"https://github.com/{OWNER}/status/actions",
        "run_url": f"https://github.com/{OWNER}/status/actions",
    }
    host_item["business"] = business_data("vps-01", host_item)
    host_item["status"] = ("success" if host_item["business"]["business_status"] == "success"
                           else "failure" if host_item["business"]["business_status"] == "failure"
                           else "unknown")
    results.append(host_item)
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
