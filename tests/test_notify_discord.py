import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from notify_discord import build_message, is_failed, is_recovered


class DiscordAlertTests(unittest.TestCase):
    def test_business_failure_is_detected_even_when_workflow_succeeded(self):
        item = {
            "name": "vps-01",
            "status": "success",
            "business": {"business_status": "failure", "business_label": "VPS-01 異常"},
        }
        self.assertTrue(is_failed(item))

    def test_workflow_failure_is_detected(self):
        self.assertTrue(is_failed({"name": "demo", "status": "failure", "business": {}}))

    def test_running_or_unknown_is_not_reported_as_recovered(self):
        self.assertFalse(is_recovered({"status": "in_progress", "business": {"business_status": "running"}}))
        self.assertFalse(is_recovered({"status": "unknown", "business": {"business_status": "unknown"}}))

    def test_success_is_recovery(self):
        self.assertTrue(is_recovered({"status": "success", "business": {"business_status": "success"}}))

    def test_message_includes_dashboard_and_does_not_ping_everyone(self):
        message = build_message(
            [{"title": "VPS-01", "reason": "端點異常", "url": "https://example.com"}],
            [{"title": "Chi Source"}],
        )
        self.assertIn("https://tsai97216.github.io/status/", message)
        self.assertIn("VPS-01", message)
        self.assertIn("已恢復正常", message)
        self.assertNotIn("@everyone", message)
        self.assertNotIn("@here", message)


if __name__ == "__main__":
    unittest.main()
