from __future__ import annotations

import re
from typing import Any

from app.config import settings
from app.repositories import delete_tips_for_period, insert_site_tip
from app.services.zodiac import ZODIAC_ORDER, extract_zodiacs_from_text, tip_type_from_text

TIP_WEIGHT = {
    "一肖": 1.0,
    "二肖": 0.85,
    "三肖": 0.7,
    "四肖": 0.55,
    "五肖": 0.45,
    "六肖": 0.35,
    "七肖": 0.3,
    "八肖": 0.25,
    "九肖": 0.2,
}


async def _fetch_text_playwright(url: str) -> str:
    from app.scrapers.browser import fetch_page_text

    return await fetch_page_text(url, wait_ms=2500)


async def _fetch_frames_concat(url: str) -> str:
    from app.scrapers.browser import fetch_page_text

    return await fetch_page_text(url, wait_ms=3500, include_frames=True)


def _chunks_for_period(text: str, period: int) -> list[str]:
    # 按“265期”切块，取目标期附近段落
    pattern = re.compile(rf"{period}期.*?(?=\d{{1,4}}期|$)", re.S)
    return [m.group(0).strip() for m in pattern.finditer(text) if m.group(0).strip()]


def _parse_and_store(period: int, site_code: str, url: str, text: str) -> int:
    chunks = _chunks_for_period(text, period)
    if not chunks:
        # 整页也可能是当期九肖表
        if str(period) in text or f"{period}期" in text:
            chunks = [text[:4000]]
        else:
            chunks = [text[:2000]]

    saved = 0
    for chunk in chunks[:12]:
        zodiacs = extract_zodiacs_from_text(chunk)
        if not zodiacs:
            continue
        tip_type = tip_type_from_text(chunk)
        insert_site_tip(
            period=period,
            site_code=site_code,
            page_url=url,
            raw_text=chunk[:5000],
            parsed_zodiacs=zodiacs,
            tip_type=tip_type,
        )
        saved += 1
    return saved


async def scrape_yanjiuyuan_tips(period: int) -> dict[str, Any]:
    urls = [settings.tip_yanjiuyuan_main, settings.site_yanjiuyuan]
    total = 0
    used: list[str] = []
    for url in urls:
        try:
            text = await _fetch_text_playwright(url)
            # 入口页可能在 iframe，再尝试从页面 frames 取文本
            if "七肖" not in text and "一肖" not in text:
                text = await _fetch_frames_concat(url)
            n = _parse_and_store(period, "yanjiuyuan", url, text)
            total += n
            used.append(url)
            if n > 0:
                break
        except Exception as exc:
            used.append(f"{url}#err:{type(exc).__name__}:{exc}")
    return {"site": "yanjiuyuan", "saved": total, "urls": used}


async def scrape_dinggeshui_tips(period: int) -> dict[str, Any]:
    urls = [
        settings.tip_dinggeshui_jiuxiao,
        settings.tip_dinggeshui_home,
        settings.site_dinggeshui,
    ]
    total = 0
    used: list[str] = []
    for url in urls:
        try:
            if "dinggeshui" in url:
                text = await _fetch_frames_concat(url)
            else:
                text = await _fetch_text_playwright(url)
            n = _parse_and_store(period, "dinggeshui", url, text)
            total += n
            used.append(url)
            if n > 0:
                break
        except Exception as exc:
            used.append(f"{url}#err:{type(exc).__name__}:{exc}")
    return {"site": "dinggeshui", "saved": total, "urls": used}


async def sync_tips(period: int) -> dict[str, Any]:
    delete_tips_for_period(period)
    y = await scrape_yanjiuyuan_tips(period)
    d = await scrape_dinggeshui_tips(period)
    return {"period": period, "yanjiuyuan": y, "dinggeshui": d}


def tip_scores_for_period(period: int, tips: list[dict[str, Any]]) -> dict[str, float]:
    scores = {z: 0.0 for z in ZODIAC_ORDER}
    for tip in tips:
        zodiacs = tip.get("parsed_zodiacs") or []
        if isinstance(zodiacs, str):
            continue
        tip_type = tip.get("tip_type") or ""
        w = TIP_WEIGHT.get(tip_type, 0.15)
        # 列表越短越集中，额外加成
        focus = 1.0 / max(len(zodiacs), 1)
        for z in zodiacs:
            if z in scores:
                scores[z] += w * focus
    return scores
