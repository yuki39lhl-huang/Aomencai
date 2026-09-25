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
    """历史页多为前端渲染，用同步 Playwright（线程）取正文。"""
    from app.scrapers.browser import fetch_page_text

    target = url or settings.history_url
    return await fetch_page_text(target, wait_ms=3500)


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


def _parse_live_payload(k: str) -> dict[str, Any] | None:
    """解析 data.txt 的 k 字段。

    已开奖示例: 264,10,06,08,31,22,24,21,265,09,22,二,21点32分
    未开奖占位: 265,K,J,③,④,⑤,开,奖,266,09,23,三,21点32分
    """
    parts = [x.strip() for x in k.split(",") if x.strip()]
    if len(parts) < 8:
        return None
    if not parts[0].isdigit():
        return None
    period = int(parts[0])
    ball_parts = parts[1:8]
    if all(p.isdigit() for p in ball_parts):
        nums = [int(p) for p in ball_parts]
        plains, special = nums[:6], nums[6]
        next_period = int(parts[8]) if len(parts) > 8 and parts[8].isdigit() else period + 1
        return {
            "drawn": True,
            "period": period,
            "numbers": plains,
            "special": special,
            "special_zodiac": number_to_zodiac(special, settings.lunar_year),
            "next_period": next_period,
            "waiting_period": next_period,
            "raw": k,
        }
    # 未开奖：第一部分是当期期号，后面是占位符
    waiting = period
    return {
        "drawn": False,
        "period": None,
        "numbers": None,
        "special": None,
        "special_zodiac": None,
        "next_period": waiting,
        "waiting_period": waiting,
        "raw": k,
    }


async def sync_live_data() -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=False) as client:
        resp = await client.get(settings.live_data_url)
        resp.raise_for_status()
        data = resp.json()
    k = str(data.get("k", ""))
    parsed = _parse_live_payload(k)
    if not parsed:
        return None
    if parsed["drawn"]:
        upsert_draw(
            period=parsed["period"],
            draw_date=datetime.now().date(),
            numbers=parsed["numbers"],
            special=parsed["special"],
            special_zodiac=parsed["special_zodiac"],
            source="live",
        )
    return parsed
