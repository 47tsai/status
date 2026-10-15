import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from notify_discord import (build_message, calculate_alert_changes, is_failed, is_recovered, normalize_active_failures)
from update_status import normalize_run_status, stale_fallback, inspect_page_content, format_unknown_health_detail


class DiscordAlertTests(unittest.TestCase):
    def test_malformed_alert_state_is_ignored_safely(self):
        self.assertEqual(normalize_active_failures(None), {})
        self.assertEqual(normalize_active_failures([]), {})
        self.assertEqual(normalize_active_failures({"active_failures": []}), {})
        self.assertEqual(
            normalize_active_failures({"active_failures": {
                "good": {"title": "Project"}, "bad": "not a record", 7: {"title": "invalid key"}
            }}),
            {"good": {"title": "Project"}},
        )

    def test_unknown_or_missing_project_does_not_clear_active_alert(self):
        previous = {"vps-01": {"name": "vps-01", "title": "VPS-01", "reason": "端點異常", "url": ""}}
        current = {
            "vps-01": {"name": "vps-01", "status": "unknown",
                       "business": {"business_status": "unknown", "business_label": "資料未知"}}
        }
        new, recovered, active = calculate_alert_changes(current, previous)
        self.assertEqual(new, [])
        self.assertEqual(recovered, [])
        self.assertIn("vps-01", active)

        new, recovered, active = calculate_alert_changes({}, previous)
        self.assertEqual(new, [])
        self.assertEqual(recovered, [])
        self.assertIn("vps-01", active)

    def test_explicit_success_clears_active_alert_once(self):
        previous = {"vps-01": {"name": "vps-01", "title": "VPS-01", "reason": "端點異常", "url": ""}}
        current = {
            "vps-01": {"name": "vps-01", "status": "success",
                       "business": {"business_status": "success", "business_label": "正常"}}
        }
        new, recovered, active = calculate_alert_changes(current, previous)
        self.assertEqual(new, [])
        self.assertEqual([item["name"] for item in recovered], ["vps-01"])
        self.assertEqual(active, {})

    def test_existing_failure_does_not_repeat_as_new_alert(self):
        item = {"name": "demo", "status": "failure", "business": {"business_status": "failure"}}
        previous = {"demo": {"name": "demo", "title": "demo", "reason": "failure", "url": ""}}
        new, recovered, active = calculate_alert_changes({"demo": item}, previous)
        self.assertEqual(new, [])
        self.assertEqual(recovered, [])
        self.assertIn("demo", active)

    def test_business_failure_is_detected_even_when_workflow_succeeded(self):
        item = {
            "name": "vps-01",
            "status": "success",
            "business": {"business_status": "failure", "business_label": "VPS-01 異常"},
        }
        self.assertTrue(is_failed(item))

    def test_workflow_failure_is_detected(self):
        self.assertTrue(is_failed({"name": "demo", "status": "failure", "business": {}}))

    def test_completed_workflow_uses_conclusion_not_literal_completed_status(self):
        self.assertEqual(normalize_run_status({"status": "completed", "conclusion": "success"}), "success")
        self.assertEqual(normalize_run_status({"status": "completed", "conclusion": "failure"}), "failure")
        self.assertEqual(normalize_run_status({"status": "completed", "conclusion": None}), "unknown")

    def test_live_workflow_keeps_live_status(self):
        self.assertEqual(normalize_run_status({"status": "in_progress", "conclusion": None}), "in_progress")
        self.assertEqual(normalize_run_status(None), "unknown")

    def test_health_check_accepts_normal_html_page(self):
        result = inspect_page_content(200, 'text/html', '<html><head><title>Chi Source</title></head><body>OK</body></html>', 'https://ipa.chi.qzz.io/')
        self.assertTrue(result['ok'])
        self.assertEqual(result['title'], 'Chi Source')

    def test_health_check_rejects_http_200_with_empty_body(self):
        result = inspect_page_content(200, 'text/html', '   ', 'https://example.com/')
        self.assertFalse(result['ok'])
        self.assertIn('空', result['reason'])

    def test_health_check_rejects_http_200_error_page(self):
        result = inspect_page_content(200, 'text/html', '<html><title>502 Bad Gateway</title><body>upstream error</body></html>', 'https://example.com/')
        self.assertFalse(result['ok'])
        self.assertIn('錯誤', result['reason'])

    def test_unknown_health_detail_avoids_repeating_status_phrase(self):
        detail = format_unknown_health_detail({"content_reason": "HTML 缺少 title，內容狀態未能確認", "status": 200})
        self.assertEqual(detail, "狀態未確認 · HTML 缺少 title · HTTP 200")

    def test_unknown_health_detail_has_fallback_reason(self):
        detail = format_unknown_health_detail({"status": 200})
        self.assertEqual(detail, "狀態未確認 · 回應內容不足以確認頁面健康 · HTTP 200")

    def test_unknown_health_detail_includes_safe_html_signals(self):
        detail = format_unknown_health_detail({
            "content_reason": "HTML 缺少 title，內容狀態未能確認",
            "content_signals": ["script", "app-root", "viewport"],
            "status": 200,
        })
        self.assertEqual(detail, "狀態未確認 · HTML 缺少 title（頁面包含 script、app/root 容器、viewport） · HTTP 200")

    def test_health_check_marks_titleless_html_unknown_not_failed(self):
        result = inspect_page_content(200, 'text/html', '<html><head><meta name="viewport" content="width=device-width"><script src="/app.js"></script></head><body><div id="app"></div></body></html>', 'https://example.com/')
        self.assertIsNone(result['ok'])
        self.assertFalse(result['protected'])
        self.assertIn('未能確認', result['reason'])
        self.assertEqual(result['signals'], ["script", "app-root", "viewport"])

    def test_health_check_marks_protected_page_unknown(self):
        result = inspect_page_content(200, 'text/html', '<html><title>Protected</title><body>Access policy login</body></html>', 'https://example.com/cdn-cgi/access/login')
        self.assertIsNone(result['ok'])
        self.assertTrue(result['protected'])

    def test_api_error_preserves_card_but_marks_data_unknown(self):
        previous = {
            "name": "demo", "status": "success",
            "business": {"business_status": "success", "business_label": "正常", "metrics": [], "note": "原始說明"},
        }
        fallback = stale_fallback({"name": "demo"}, previous, "HTTP 502")
        self.assertEqual(fallback["status"], "unknown")
        self.assertEqual(fallback["business"]["business_status"], "unknown")
        self.assertIn("上次資料", fallback["business"]["business_label"])
        self.assertIn("HTTP 502", fallback["monitor_warning"])
        self.assertIsNone(stale_fallback({"name": "new"}, None, "HTTP 502"))

    def test_running_or_unknown_is_not_reported_as_recovered(self):
        self.assertFalse(is_recovered({"status": "in_progress", "business": {"business_status": "running"}}))
        self.assertFalse(is_recovered({"status": "unknown", "business": {"business_status": "unknown"}}))

    def test_success_is_recovery(self):
        self.assertTrue(is_recovered({"status": "success", "business": {"business_status": "success"}}))
        self.assertTrue(is_recovered({"status": "success", "business": {}}))

    def test_workflow_success_does_not_mask_unknown_business_state(self):
        self.assertFalse(is_recovered({"status": "success", "business": {"business_status": "unknown"}}))
        self.assertFalse(is_recovered({"status": "success", "business": {"business_status": "running"}}))

    def test_workflow_success_does_not_mask_business_failure(self):
        self.assertFalse(is_recovered({"status": "success", "business": {"business_status": "failure"}}))

    def test_message_includes_dashboard_and_does_not_ping_everyone(self):
        message = build_message(
            [{"title": "VPS-01", "reason": "端點異常", "url": "https://example.com"}],
            [{"title": "Chi Source"}],
        )
        self.assertIn("https://status.chi.qzz.io/", message)
        self.assertIn("VPS-01", message)
        self.assertIn("已恢復正常", message)
        self.assertNotIn("@everyone", message)
        self.assertNotIn("@here", message)


if __name__ == "__main__":
    unittest.main()
