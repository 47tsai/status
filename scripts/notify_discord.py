#!/usr/bin/env python3
"""Send deduplicated project-failure alerts to a Discord webhook."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATUS_PATH = Path("status.json")
STATE_PATH = Path("alert-state.json")
FAILURE_STATUSES = {"failure", "timed_out", "action_required", "startup_failure"}


def is_failed(item):
    business = item.get("business") or {}
    return item.get("status") in FAILURE_STATUSES or business.get("business_status") in FAILURE_STATUSES


def is_recovered(item):
    """Require explicit success from the same source that can report business health."""
    business = item.get("business") or {}
    if is_failed(item):
        return False
    business_status = business.get("business_status")
    # A generic green Actions run must not hide an unknown or still-failing
    # business result (for example, a reachable workflow but unhealthy VPS).
    if business_status:
        return business_status == "success"
    return item.get("status") == "success"


def failure_record(item):
    business = item.get("business") or {}
    return {
        "name": item.get("name") or item.get("full_name") or "unknown",
        "title": business.get("title") or item.get("workflow") or item.get("name") or "未知專案",
        "reason": business.get("business_label") or item.get("status") or "狀態失敗",
        "url": item.get("run_url") or item.get("runs_url") or item.get("html_url") or "",
    }


def read_json(path, default):
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def post_discord(webhook_url, content):
    payload = json.dumps({"content": content[:1900], "allowed_mentions": {"parse": []}}).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "ChiStatus/1.0"}
    for attempt in range(3):
        request = urllib.request.Request(webhook_url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if 200 <= response.status < 300:
                    return
                raise RuntimeError(f"Discord webhook returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            # Retry rate limits and transient server errors, but fail fast for
            # invalid webhook URLs or other client errors.
            if exc.code != 429 and exc.code < 500:
                raise
            if attempt == 2:
                raise
            retry_after = exc.headers.get("Retry-After", "")
            try:
                delay = min(30, max(1, float(retry_after)))
            except (TypeError, ValueError):
                delay = 2 ** attempt
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def build_message(new_failures, recovered):
    lines = ["**Chi Status 告警**"]
    if new_failures:
        lines.append("🔴 **新發現異常**")
        for item in new_failures[:10]:
            line = f"• **{item['title']}**：{item['reason']}"
            if item.get("url"):
                line += f"\n  {item['url']}"
            lines.append(line)
        if len(new_failures) > 10:
            lines.append(f"另有 {len(new_failures) - 10} 個新異常，請查看儀表板。")
    if recovered:
        lines.append("🟢 **已恢復正常**")
        for item in recovered[:10]:
            lines.append(f"• **{item['title']}**")
        if len(recovered) > 10:
            lines.append(f"另有 {len(recovered) - 10} 個專案已恢復。")
    lines.append("儀表板：https://status.chi.qzz.io/")
    lines.append("時間：" + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    return "\n".join(lines)


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL 未設定；略過 Discord 通知，且不更新告警狀態。")
        return 0

    payload = read_json(STATUS_PATH, {})
    items = payload.get("repositories", [])
    if not isinstance(items, list):
        print("status.json 的 repositories 格式錯誤；略過通知。", file=sys.stderr)
        return 0

    current = {str(item.get("name") or item.get("full_name")): item for item in items
               if isinstance(item, dict) and (item.get("name") or item.get("full_name"))}
    current_failures = {name: failure_record(item) for name, item in current.items() if is_failed(item)}
    previous_state = read_json(STATE_PATH, {"active_failures": {}})
    previous = previous_state.get("active_failures", {})
    if not isinstance(previous, dict):
        previous = {}

    new_failures = [record for name, record in current_failures.items() if name not in previous]
    recovered = [previous[name] for name in previous
                 if name in current and name not in current_failures and is_recovered(current[name])]

    # Keep the prior alert active if a project is missing or only has an unknown/running
    # result. Missing data and an in-progress run are not proof that the issue recovered.
    next_active = dict(current_failures)
    for name, record in previous.items():
        if name not in current or (name not in current_failures and not is_recovered(current[name])):
            next_active[name] = record

    if not new_failures and not recovered:
        print(f"沒有新的異常或恢復事件；目前追蹤 {len(next_active)} 個異常。")
        STATE_PATH.write_text(json.dumps({"active_failures": next_active}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    message = build_message(new_failures, recovered)
    try:
        post_discord(webhook_url, message)
    except Exception as exc:
        # Do not advance the state on delivery failure. The next scheduled run retries.
        print(f"Discord 通知傳送失敗，保留告警狀態供下次重試：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 0

    STATE_PATH.write_text(json.dumps({"active_failures": next_active}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Discord 通知已送出：新異常 {len(new_failures)}，恢復 {len(recovered)}。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
