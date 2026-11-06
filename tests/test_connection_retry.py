import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.scrapers import tips as tips_mod
from app.sites import TipSite, all_tip_fetch_urls


class ConnectionRetryTest(unittest.TestCase):
    def test_dinggeshui_urls_prefer_jiuxiao_not_homepage(self):
        site = next(s for s in tips_mod.enabled_tip_sites() if s.code == "dinggeshui")
        urls = all_tip_fetch_urls(site)
        self.assertTrue(urls[0].endswith("%E4%B9%9D%E8%82%96.htm") or "九肖" in urls[0])
        self.assertTrue(all("dinggeshui.com" not in u for u in urls))

    def test_fetch_retries_once_on_connection_closed(self):
        calls = {"n": 0}

        async def flaky(_url, prefer_frames=False):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("net::ERR_CONNECTION_CLOSED")
            return "310期九肖鼠牛虎兔龙蛇马羊猴"

        with (
            patch.object(tips_mod, "_fetch_text", side_effect=flaky),
            patch.object(tips_mod, "_CONNECTION_RETRY_SLEEP_SEC", 0),
        ):
            text, retried = asyncio.run(
                tips_mod._fetch_text_retry_connection("https://example.test/", True)
            )
        self.assertTrue(retried)
        self.assertEqual(calls["n"], 2)
        self.assertIn("九肖", text)

    def test_fetch_marks_retried_when_second_also_fails(self):
        async def always_closed(_url, prefer_frames=False):
            raise RuntimeError("Connection reset by peer")

        with (
            patch.object(tips_mod, "_fetch_text", side_effect=always_closed),
            patch.object(tips_mod, "_CONNECTION_RETRY_SLEEP_SEC", 0),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(tips_mod._fetch_text_retry_connection("https://example.test/", False))
        self.assertTrue(getattr(ctx.exception, "_tip_connection_retried", False))

    def test_scrape_records_connection_closed_retried(self):
        site = TipSite(
            code="dinggeshui",
            name="定个水",
            entry_urls=(),
            tip_urls=("https://333810.com/zl/x.htm",),
            prefer_frames=False,
            max_extra_links=0,
        )

        async def always_closed(_url, prefer_frames=False):
            raise RuntimeError("ERR_CONNECTION_CLOSED")

        with (
            patch.object(tips_mod, "_fetch_text", side_effect=always_closed),
            patch.object(tips_mod, "_CONNECTION_RETRY_SLEEP_SEC", 0),
        ):
            out = asyncio.run(tips_mod.scrape_tip_site(310, site, {}))
        self.assertEqual(out["fail_reason"], "connection_closed")
        self.assertIn("retried=1", out["fail_detail"])
        self.assertEqual(out["saved"], 0)


if __name__ == "__main__":
    unittest.main()
