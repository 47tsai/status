import unittest
from datetime import datetime, timezone

from scripts.update_status import classify_checkin_result, parse_checkin_record, reset_cycle_date


class ResetCycleDateTests(unittest.TestCase):
    def test_brawl_stars_before_reset_belongs_to_previous_cycle(self):
        self.assertEqual(
            reset_cycle_date(datetime(2026, 10, 16, 15, 59), 16),
            datetime(2026, 10, 15).date(),
        )

    def test_brawl_stars_at_reset_starts_new_cycle(self):
        self.assertEqual(
            reset_cycle_date(datetime(2026, 10, 16, 16, 0), 16),
            datetime(2026, 10, 16).date(),
        )

    def test_brawl_stars_after_reset_stays_in_new_cycle(self):
        self.assertEqual(
            reset_cycle_date(datetime(2026, 10, 16, 16, 1), 16),
            datetime(2026, 10, 16).date(),
        )

    def test_midnight_reset_before_midnight(self):
        self.assertEqual(
            reset_cycle_date(datetime(2026, 10, 16, 23, 59), 0),
            datetime(2026, 10, 16).date(),
        )

    def test_midnight_reset_at_midnight_starts_new_cycle(self):
        self.assertEqual(
            reset_cycle_date(datetime(2026, 10, 17, 0, 0), 0),
            datetime(2026, 10, 17).date(),
        )

    def test_aware_timestamp_is_converted_to_taipei_before_cycle_check(self):
        # 08:00 UTC is 16:00 in Taiwan, exactly the Brawl Stars reset.
        self.assertEqual(
            reset_cycle_date(datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc), 16),
            datetime(2026, 10, 16).date(),
        )

    def test_aware_timestamp_just_before_taipei_reset(self):
        # 07:59 UTC is 15:59 in Taiwan, still the previous claim cycle.
        self.assertEqual(
            reset_cycle_date(datetime(2026, 10, 16, 7, 59, tzinfo=timezone.utc), 16),
            datetime(2026, 10, 15).date(),
        )


class CheckinFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 10, 0)

    def test_yesterdays_success_is_unknown_after_midnight(self):
        result = classify_checkin_result("2026-10-15 23:59:59", "簽到成功", self.now)
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["displayed_result"], "紀錄過期，尚未確認今日簽到")
        self.assertEqual(result["tone"], "normal")

    def test_todays_success_is_success(self):
        result = classify_checkin_result("2026-10-16 00:00:00", "簽到成功", self.now)
        self.assertEqual(result["business_status"], "success")
        self.assertEqual(result["displayed_result"], "簽到成功")
        self.assertEqual(result["tone"], "good")

    def test_todays_failure_is_failure(self):
        result = classify_checkin_result("2026-10-16 09:30:00", "簽到失敗", self.now)
        self.assertEqual(result["business_status"], "failure")
        self.assertEqual(result["tone"], "bad")

    def test_future_timestamp_never_claims_success(self):
        result = classify_checkin_result("2026-10-16 23:59:59", "簽到成功", self.now)
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["business_label"], "紀錄時間晚於目前時間，無法確認簽到結果")
        self.assertEqual(result["tone"], "normal")

    def test_conflicting_success_and_failure_markers_remain_unknown(self):
        result = classify_checkin_result(
            "2026-10-16 09:30:00", "簽到成功，但其他帳號簽到失敗", self.now
        )
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["business_label"], "簽到結果文字互相矛盾，無法判讀")
        self.assertEqual(result["tone"], "normal")

    def test_negated_success_phrase_never_claims_success(self):
        result = classify_checkin_result("2026-10-16 09:30:00", "未簽到成功", self.now)
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["tone"], "normal")

    def test_missing_timestamp_never_claims_success(self):
        result = classify_checkin_result(None, "簽到成功", self.now)
        self.assertEqual(result["business_status"], "unknown")
        self.assertIn("缺少", result["displayed_result"])

    def test_unrecognized_status_today_remains_unknown(self):
        result = classify_checkin_result("2026-10-16 09:30:00", "執行完成，結果未知", self.now)
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["tone"], "normal")

    def test_aware_utc_timestamp_uses_taipei_calendar_day(self):
        # 2026-10-15 16:30 UTC is 2026-10-16 00:30 in Taiwan.
        result = classify_checkin_result(
            "2026-10-15T16:30:00+00:00", "簽到成功", self.now
        )
        self.assertEqual(result["business_status"], "success")


    def test_malformed_timestamp_never_claims_success(self):
        result = classify_checkin_result("not-a-date", "簽到成功", self.now)
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["business_label"], "時間戳記格式錯誤，無法確認今日結果")
        self.assertEqual(result["displayed_result"], "簽到時間無法解析，請檢查來源紀錄格式")
        self.assertEqual(result["tone"], "normal")

    def test_impossible_calendar_date_is_not_mislabeled_as_expired(self):
        result = classify_checkin_result("2026-99-99 12:00:00", "簽到成功", self.now)
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["business_label"], "時間戳記格式錯誤，無法確認今日結果")
        self.assertEqual(result["tone"], "normal")

    def test_unavailable_source_has_distinct_message_from_expired_record(self):
        result = classify_checkin_result(
            None, None, self.now, source_available=False
        )
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["business_label"], "來源紀錄讀取失敗，無法確認簽到結果")
        self.assertIn("無法讀取來源檔", result["displayed_result"])
        self.assertEqual(result["tone"], "normal")

    def test_unavailable_source_record_never_claims_success(self):
        timestamp, status_line = parse_checkin_record(None)
        result = classify_checkin_result(timestamp, status_line, self.now)
        self.assertEqual(result["business_status"], "unknown")
        self.assertEqual(result["tone"], "normal")
        self.assertIn("缺少", result["displayed_result"])


class CheckinRecordParsingTests(unittest.TestCase):
    def test_apktw_activity_format_parses_last_run_and_result(self):
        record = "# APK.TW Check-in Activity\n\nLast run: 2026-10-16 16:45:07\n\nResult: ✅ 簽到成功\n"
        self.assertEqual(parse_checkin_record(record), ("2026-10-16 16:45:07", "✅ 簽到成功"))

    def test_bahamut_row_timestamp_overrides_unrelated_last_run(self):
        record = (
            "# 巴哈姆特自動簽到\n"
            "Last run: 2026-10-16 23:59:59\n"
            "| 帳號 | 上次簽到時間 | 簽到結果 |\n"
            "| --- | --- | --- |\n"
            "| 帳號 | 2026-10-15 23:58:00 | ✅ 簽到成功 |\n"
        )
        self.assertEqual(parse_checkin_record(record), ("2026-10-15 23:58:00", "✅ 簽到成功"))

    def test_empty_or_unrecognized_record_does_not_invent_result(self):
        self.assertEqual(parse_checkin_record(""), (None, None))
        self.assertEqual(parse_checkin_record("# no status here"), (None, None))

    def test_failure_row_is_parsed(self):
        record = "| 帳號 | 上次簽到時間 | 簽到結果 |\n|---|---|---|\n| A | 2026-10-16 08:00:00 | ❌ 簽到失敗 |"
        self.assertEqual(parse_checkin_record(record), ("2026-10-16 08:00:00", "❌ 簽到失敗"))


if __name__ == "__main__":
    unittest.main()
