from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

import httpx

from app.config import settings
from app.repositories import upsert_draw
from app.services.zodiac import number_to_zodiac

NUM_ZODIAC_RE = re.compile(r"(?P<num>\d{1,2})\s*(?P<zodiac>[鼠牛虎兔龙蛇马羊猴鸡狗猪])")
PERIOD_BLOCK_RE = re.compile(
    r"(?P<period>\d{1,4})期\s*[（(]\s*开奖时间\s*[:：]\s*(?P<dt>\d{4}-\d{2}-\d{2})\s*[）)]"
    r"(?P<body>.*?)(?=\d{1,4}期\s*[（(]\s*开奖时间|$)",
    re.S,
)


def parse_history_text(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for m in PERIOD_BLOCK_RE.finditer(text):
        period = int(m.group("period"))
        draw_date = date.fromisoformat(m.group("dt"))
        body = m.group("body")
        pairs = NUM_ZODIAC_RE.findall(body)
        if len(pairs) < 7:
            continue
        nums = [int(p[0]) for p in pairs[:7]]
        special = nums[6]
        plains = nums[:6]
        results.append(
            {
                "period": period,
                "draw_date": draw_date,
                "numbers": plains,
                "special": special,
                "special_zodiac": number_to_zodiac(special, settings.lunar_year),
            }
        )
    return results


async def fetch_history_html(url: str | None = None) -> str:
    """历史页多为前端渲染，统一用 Playwright 取正文。"""
    target = url or settings.history_url
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(target, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(3500)
        text = await page.inner_text("body")
        await browser.close()
        return text


async def sync_history(url: str | None = None) -> dict[str, Any]:
    text = await fetch_history_html(url)
    rows = parse_history_text(text)
    for row in rows:
        upsert_draw(
            period=row["period"],
            draw_date=row["draw_date"],
            numbers=row["numbers"],
            special=row["special"],
            special_zodiac=row["special_zodiac"],
            source="history",
        )
    return {"count": len(rows), "max_period": max((r["period"] for r in rows), default=None)}


async def sync_live_data() -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=False) as client:
        resp = await client.get(settings.live_data_url)
        resp.raise_for_status()
        data = resp.json()
    k = str(data.get("k", ""))
    parts = [x.strip() for x in k.split(",") if x.strip()]
    # 例: 264,10,06,08,31,22,24,21,265,09,22,二,21点32分
    if len(parts) < 8:
        return None
    period = int(parts[0])
    nums = [int(x) for x in parts[1:8]]
    plains, special = nums[:6], nums[6]
    zodiac = number_to_zodiac(special, settings.lunar_year)
    upsert_draw(
        period=period,
        draw_date=datetime.now().date(),
        numbers=plains,
        special=special,
        special_zodiac=zodiac,
        source="live",
    )
    next_period = int(parts[8]) if len(parts) > 8 and parts[8].isdigit() else period + 1
    return {
        "period": period,
        "numbers": plains,
        "special": special,
        "special_zodiac": zodiac,
        "next_period": next_period,
        "raw": k,
    }
