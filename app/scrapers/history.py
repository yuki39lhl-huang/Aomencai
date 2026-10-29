from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.config import settings
from app.repositories import get_draw, upsert_draw
from app.services.zodiac import lunar_year_for, number_to_zodiac

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
                "special_zodiac": number_to_zodiac(special, lunar_year_for(draw_date)),
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


def _payload_month_day(parts: list[str]) -> date | None:
    """data.txt 里期号后的月、日。年份按今天附近取，跨年时前后挪一年。"""
    if len(parts) < 11:
        return None
    if not (parts[9].isdigit() and parts[10].isdigit()):
        return None
    month, day = int(parts[9]), int(parts[10])
    today = date.today()
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None
    if candidate - today > timedelta(days=180):
        candidate = date(today.year - 1, month, day)
    elif today - candidate > timedelta(days=180):
        candidate = date(today.year + 1, month, day)
    return candidate


def live_draw_date_from_parts(parts: list[str], *, drawn: bool) -> date | None:
    """已开奖：payload 日期是下一期，本期开奖日取前一天。未开奖：日期就是当期。"""
    payload_day = _payload_month_day(parts)
    if payload_day is None:
        return None
    if drawn:
        return payload_day - timedelta(days=1)
    return payload_day


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
        draw_date = live_draw_date_from_parts(parts, drawn=True)
        return {
            "drawn": True,
            "period": period,
            "numbers": plains,
            "special": special,
            "draw_date": draw_date,
            "special_zodiac": (
                number_to_zodiac(special, lunar_year_for(draw_date))
                if draw_date is not None
                else None
            ),
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
        "draw_date": live_draw_date_from_parts(parts, drawn=False),
        "special_zodiac": None,
        "next_period": waiting,
        "waiting_period": waiting,
        "raw": k,
    }


async def sync_live_data() -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=False) as client:
        resp = await client.get(settings.live_data_url)
        resp.raise_for_status()
        body = resp.content.lstrip()
        if not body.startswith((b"{", b"[")):
            kind = resp.headers.get("content-type") or "unknown"
            raise RuntimeError(f"实时开奖返回的不是 JSON（{kind}）")
        data = resp.json()
    k = str(data.get("k", ""))
    parsed = _parse_live_payload(k)
    if not parsed:
        return None
    if parsed["drawn"]:
        period = int(parsed["period"])
        existing = get_draw(period)
        # 已有 history 行：保留它的开奖日和特码生肖，不用「今天」盖掉
        if existing and existing.get("source") == "history" and existing.get("draw_date"):
            draw_date = existing["draw_date"]
            if isinstance(draw_date, datetime):
                draw_date = draw_date.date()
            special_zodiac = existing.get("special_zodiac") or number_to_zodiac(
                int(parsed["special"]), lunar_year_for(draw_date)
            )
            source = "history"
        else:
            draw_date = parsed.get("draw_date")
            if draw_date is None and existing and existing.get("draw_date"):
                draw_date = existing["draw_date"]
                if isinstance(draw_date, datetime):
                    draw_date = draw_date.date()
            if draw_date is None:
                draw_date = date.today()
            special_zodiac = number_to_zodiac(int(parsed["special"]), lunar_year_for(draw_date))
            source = "live"
        parsed["draw_date"] = draw_date
        parsed["special_zodiac"] = special_zodiac
        upsert_draw(
            period=period,
            draw_date=draw_date,
            numbers=parsed["numbers"],
            special=parsed["special"],
            special_zodiac=special_zodiac,
            source=source,
        )
    return parsed
