import asyncio
import unittest
from unittest.mock import MagicMock, patch

from app.scrapers import tips as tips_mod
from app.sites import TipSite


class TipParallelSyncTest(unittest.TestCase):
    def test_concurrency_cap_constant(self):
        self.assertEqual(tips_mod._TIP_SCRAPE_CONCURRENCY, 5)
        self.assertEqual(tips_mod._SITE_SCRAPE_TIMEOUT_SEC, 75)

    def test_sync_tips_runs_sites_concurrently_then_replace_once(self):
        sites = [
            TipSite(code="a", name="A", entry_urls=("https://a.example/",), prefer_frames=False),
            TipSite(code="b", name="B", entry_urls=("https://b.example/",), prefer_frames=False),
            TipSite(code="c", name="C", entry_urls=("https://c.example/",), prefer_frames=False),
        ]
        active = 0
        peak = 0

        async def fake_scrape(period, site, prior_seen):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.05)
            active -= 1
            return {
                "site": site.code,
                "name": site.name,
                "saved": 1,
                "rows": [
                    {
                        "page_url": site.entry_urls[0],
                        "raw_text": "x",
                        "parsed_zodiacs": ["马"],
                        "tip_type": "一肖",
                        "play_scope": "bao_xiao",
                        "first_seen_at": None,
                    }
                ],
                "urls": [site.entry_urls[0]],
                "strategies": ["test"],
                "note": "",
                "fail_reason": None,
                "fail_detail": "",
            }

        replace = MagicMock()
        with (
            patch.object(tips_mod, "enabled_tip_sites", return_value=sites),
            patch.object(tips_mod, "list_tip_first_seen", return_value={}),
            patch.object(tips_mod, "list_tips", return_value=[]),
            patch.object(tips_mod, "scrape_tip_site", side_effect=fake_scrape),
            patch.object(tips_mod, "record_site_scrape") as record,
            patch.object(tips_mod, "replace_site_tips", replace),
        ):
            record.return_value = {
                "fail_streak": 0,
                "alert": False,
                "reuse": None,
                "counted": False,
            }
            out = asyncio.run(tips_mod.sync_tips(308))

        self.assertEqual(out["saved_total"], 3)
        self.assertEqual(out["concurrency"], 5)
        self.assertGreaterEqual(peak, 2)
        replace.assert_called_once()
        fresh = replace.call_args[0][1]
        self.assertEqual(set(fresh), {"a", "b", "c"})

    def test_timeout_item_keeps_other_sites(self):
        sites = [
            TipSite(code="slow", name="Slow", entry_urls=("https://slow.example/",)),
            TipSite(code="ok", name="Ok", entry_urls=("https://ok.example/",)),
        ]

        async def fake_scrape(period, site, prior_seen):
            if site.code == "slow":
                await asyncio.sleep(10)
            return {
                "site": site.code,
                "name": site.name,
                "saved": 1,
                "rows": [
                    {
                        "page_url": site.entry_urls[0],
                        "raw_text": "x",
                        "parsed_zodiacs": ["马"],
                        "tip_type": "一肖",
                        "play_scope": "bao_xiao",
                        "first_seen_at": None,
                    }
                ],
                "urls": [],
                "strategies": [],
                "note": "",
                "fail_reason": None,
                "fail_detail": "",
            }

        with (
            patch.object(tips_mod, "enabled_tip_sites", return_value=sites),
            patch.object(tips_mod, "list_tip_first_seen", return_value={}),
            patch.object(tips_mod, "list_tips", return_value=[]),
            patch.object(tips_mod, "scrape_tip_site", side_effect=fake_scrape),
            patch.object(tips_mod, "_SITE_SCRAPE_TIMEOUT_SEC", 0.05),
            patch.object(tips_mod, "record_site_scrape") as record,
            patch.object(tips_mod, "replace_site_tips") as replace,
        ):
            def _status(code, *, ok, **kwargs):
                return {
                    "fail_streak": 0 if ok else 1,
                    "alert": False,
                    "reuse": None if ok else "prior_period",
                    "counted": not ok,
                }

            record.side_effect = lambda code, **kw: _status(code, **kw)
            out = asyncio.run(tips_mod.sync_tips(308))

        by_site = {s["site"]: s for s in out["sites"]}
        self.assertEqual(by_site["slow"]["fail_reason"], "timeout")
        self.assertEqual(out["saved_total"], 1)
        replace.assert_called_once()
        self.assertIn("ok", replace.call_args[0][1])
        self.assertNotIn("slow", replace.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
