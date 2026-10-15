#!/usr/bin/env python3
"""Collect workflow health and project-specific business outcomes for the status dashboard."""
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from html import unescape

OWNER = "tsai97216"
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
    "sc-auto-claim": {"kind": "claim", "title": "荒野亂鬥自動領取", "description": "兩個帳號的實際領取結果與最近成功時間", "icon": "🎮"},
    "free-game": {"kind": "freegame", "title": "免費遊戲通知", "description": "RSS 掃描、已處理遊戲與文章去重狀態", "icon": "🕹"},
    "apktwsign": {"kind": "checkin", "title": "APK.TW 自動簽到", "description": "網站回報的簽到結果與最近紀錄", "icon": "✓"},
    "bahasign": {"kind": "checkin", "title": "巴哈姆特自動簽到", "description": "網站回報的簽到結果與最近紀錄", "icon": "✓"},
    "chi-source": {"kind": "deploy", "title": "Chi Source", "description": "AltStore 來源網站建置與部署", "icon": "⌘"},
    "chi-source-personal": {"kind": "deploy", "title": "Chi Source Personal", "description": "個人化 AltStore 來源部署", "icon": "⌘"},
    "h": {"kind": "deploy", "title": "H 連結工具", "description": "工具網站建置與部署", "icon": "↗"},
    "nav": {"kind": "deploy", "title": "Chi 導航站", "description": "導航網站建置與部署", "icon": "⌖"},
    "nav-n": {"kind": "deploy", "title": "Chi 導航站（舊版）", "description": "舊版導航站最近一次部署", "icon": "⌖"},
    "chi-brand": {"kind": "deploy", "title": "Chi Brand", "description": "品牌展示頁建置與部署", "icon": "◇"},
    "merch": {"kind": "deploy", "title": "Merch 商品資料", "description": "商品資料更新與部署流程", "icon": "▦"},
    "merch-old": {"kind": "deploy", "title": "Merch 舊版", "description": "舊版商品網站部署狀態", "icon": "▦"},
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

def business_data(repo_name, run):
    kind = PROFILES.get(repo_name, {}).get("kind", "generic")
    result = {"kind": kind, "title": PROFILES.get(repo_name, {}).get("title", repo_name),
              "description": PROFILES.get(repo_name, {}).get("description", "最近一次 Workflow 執行狀況"),
              "icon": PROFILES.get(repo_name, {}).get("icon", "◉"),
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
        games = sum(1 for x in entries if str(x).startswith("game|"))
        articles = sum(1 for x in entries if str(x).startswith("article|"))
        result["business_status"] = "success" if run and run.get("status") == "success" else "failure" if run and run.get("status") == "failure" else "unknown"
        result["business_label"] = "最近掃描流程成功" if result["business_status"] == "success" else "最近掃描流程失敗" if result["business_status"] == "failure" else "掃描結果待確認"
        result["metrics"] = [metric("已處理遊戲", games), metric("已處理文章", articles), metric("去重紀錄", len(entries))]
        result["details"] = [{"label": "狀態檔", "result": "可讀取" if isinstance(processed, list) else "無法讀取", "time": "以 Workflow 執行時間為準", "tone": "good" if isinstance(processed, list) else "bad"}]
        result["note"] = "目前倉庫只保存累積去重清單，尚未保存「本輪新增幾款／通知幾則」的獨立摘要；此處不會把累積數誤當成單輪成果。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/blob/main/data/processed.json"
    elif kind == "checkin":
        record = raw(repo_name, "activity.md") if repo_name == "apktwsign" else raw(repo_name, "README.md")
        timestamp, status_line = None, None
        if record:
            for line in record.splitlines():
                if line.lower().startswith("last run:"):
                    timestamp = line.split(":", 1)[1].strip()
                if "簽到成功" in line or "今日已簽到" in line or "簽到失敗" in line or "執行完成，結果未知" in line:
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
    elif kind == "deploy":
        status = (run or {}).get("status")
        result["business_status"] = "success" if status == "success" else "failure" if status == "failure" else "running" if status in ("in_progress", "queued", "waiting", "requested") else "unknown"
        result["business_label"] = {"success": "最近部署成功", "failure": "最近部署失敗", "running": "部署進行中"}.get(result["business_status"], "部署狀態未知")
        result["metrics"] = [metric("部署結果", result["business_label"], "good" if status == "success" else "bad" if status == "failure" else "normal"),
                             metric("分支", (run or {}).get("head_branch") or "－"),
                             metric("觸發方式", (run or {}).get("event") or "－")]
        result["details"] = [{"label": "最近部署", "result": result["business_label"], "time": taipei_time((run or {}).get("updated_at")), "tone": "good" if status == "success" else "bad" if status == "failure" else "normal"}]
        result["note"] = "此類專案的主要可驗證成果是部署流程；目前監控的是 GitHub Actions 部署結果，尚未做網站 HTTP 健康檢查。"
        result["evidence_url"] = f"https://github.com/{OWNER}/{repo_name}/actions"
    else:
        status = (run or {}).get("status")
        result["business_status"] = status or "unknown"
        result["business_label"] = "最近 Workflow：" + str(status or "尚無紀錄")
        result["metrics"] = [metric("Workflow", (run or {}).get("name") or "尚無紀錄"),
                             metric("分支", (run or {}).get("head_branch") or "－")]
        result["details"] = []
        result["note"] = "尚未配置專屬業務資料解析器。"
    return result

def main():
    repos = []
    for page in range(1, 4):
        batch = get_json(f"https://api.github.com/users/{OWNER}/repos?type=public&per_page=100&page={page}&sort=updated")
        repos.extend(r for r in batch if not r.get("fork", False) and not r.get("archived", False))
        if len(batch) < 100:
            break
    results = []
    for repo in repos:
        full_name = repo["full_name"]
        try:
            data = get_json(f"https://api.github.com/repos/{full_name}/actions/runs?per_page=1")
            runs = data.get("workflow_runs", [])
            if not runs:
                continue
            run = runs[0]
            duration = None
            if run.get("run_started_at") and run.get("status") == "completed":
                start = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                duration = max(0, int((end - start).total_seconds()))
            status = run.get("conclusion") if run.get("status") == "completed" else run.get("status")
            item = {
                "name": repo["name"], "full_name": full_name, "html_url": repo["html_url"],
                "workflow": run.get("name") or run.get("display_title") or "GitHub Actions",
                "status": status, "branch": run.get("head_branch"),
                "updated_at": run.get("updated_at") or run.get("created_at"),
                "event": run.get("event"),
                "commit_message": ((run.get("head_commit") or {}).get("message") or "").splitlines()[0][:180],
                "duration_seconds": duration, "runs_url": repo["html_url"] + "/actions",
                "run_url": run.get("html_url"),
            }
            item["business"] = business_data(repo["name"], item)
            results.append(item)
        except urllib.error.HTTPError as exc:
            print(f"Skipping {full_name}: HTTP {exc.code}")
        except Exception as exc:
            print(f"Skipping {full_name}: {exc}")
    results.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(),
               "repository_count": len(results), "repositories": results}
    with open("status.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Collected workflow and project-specific business status for {len(results)} repositories.")

if __name__ == "__main__":
    main()
