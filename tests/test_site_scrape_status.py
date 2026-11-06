import unittest
from unittest.mock import MagicMock, patch

from app.repositories import record_site_scrape, scrape_failure_is_alert


class AlertThresholdTest(unittest.TestCase):
    def test_hard_reason_alerts_at_three(self):
        self.assertFalse(scrape_failure_is_alert(2, "timeout"))
        self.assertTrue(scrape_failure_is_alert(3, "timeout"))
        self.assertTrue(scrape_failure_is_alert(3, "route_page"))

    def test_soft_reason_alerts_at_five(self):
        self.assertFalse(scrape_failure_is_alert(3, "no_period"))
        self.assertFalse(scrape_failure_is_alert(4, "no_list"))
        self.assertTrue(scrape_failure_is_alert(5, "no_period"))
        self.assertTrue(scrape_failure_is_alert(5, "no_list"))


class RecordSiteScrapeTest(unittest.TestCase):
    def _cursor(self, prev: dict | None):
        cur = MagicMock()
        cur.fetchone.return_value = prev
        cm = MagicMock()
        cm.__enter__.return_value = cur
        cm.__exit__.return_value = False
        return cm, cur

    @patch("app.repositories.ensure_site_scrape_table")
    @patch("app.repositories.db_cursor")
    def test_same_period_failure_does_not_raise_streak(self, mock_db, _ensure):
        cm, cur = self._cursor(
            {"fail_streak": 2, "last_reason": "no_list", "last_period": 303, "last_fail_period": 303}
        )
        mock_db.return_value = cm
        out = record_site_scrape("stest", ok=False, period=303, reason="no_list", had_prior_tips=True)
        self.assertEqual(out["fail_streak"], 2)
        self.assertFalse(out["counted"])
        self.assertFalse(out["alert"])
        self.assertEqual(out["reuse"], "same_period")

    @patch("app.repositories.ensure_site_scrape_table")
    @patch("app.repositories.db_cursor")
    def test_new_period_failure_raises_streak(self, mock_db, _ensure):
        cm, cur = self._cursor(
            {"fail_streak": 2, "last_reason": "no_list", "last_period": 302, "last_fail_period": 302}
        )
        mock_db.return_value = cm
        out = record_site_scrape("stest", ok=False, period=303, reason="route_page", had_prior_tips=False)
        self.assertEqual(out["fail_streak"], 3)
        self.assertTrue(out["counted"])
        self.assertTrue(out["alert"])
        self.assertEqual(out["reuse"], "prior_period")

    @patch("app.repositories.ensure_site_scrape_table")
    @patch("app.repositories.db_cursor")
    def test_soft_reason_streak_three_not_alert(self, mock_db, _ensure):
        cm, cur = self._cursor(
            {"fail_streak": 2, "last_reason": "no_period", "last_period": 302, "last_fail_period": 302}
        )
        mock_db.return_value = cm
        out = record_site_scrape("stest", ok=False, period=303, reason="no_period", had_prior_tips=False)
        self.assertEqual(out["fail_streak"], 3)
        self.assertFalse(out["alert"])

    @patch("app.repositories.ensure_site_scrape_table")
    @patch("app.repositories.db_cursor")
    def test_success_clears_streak(self, mock_db, _ensure):
        cm, cur = self._cursor(
            {"fail_streak": 3, "last_reason": "timeout", "last_period": 303, "last_fail_period": 303}
        )
        mock_db.return_value = cm
        out = record_site_scrape("stest", ok=True, period=303)
        self.assertEqual(out["fail_streak"], 0)
        self.assertFalse(out["alert"])
        self.assertIsNone(out["reuse"])


if __name__ == "__main__":
    unittest.main()
