import unittest
from datetime import datetime, timezone

from scripts.update_status import reset_cycle_date


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


if __name__ == "__main__":
    unittest.main()
