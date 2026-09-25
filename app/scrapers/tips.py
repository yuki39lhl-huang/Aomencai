from __future__ import annotations

import re
from typing import Any

from app.repositories import delete_tips_for_period, insert_site_tip
from app.services.zodiac import ZODIAC_ORDER, extract_zodiacs_from_text, tip_type_from_text
from app.sites import TipSite, all_tip_fetch_urls, enabled_tip_sites

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

# 抽取时只认这些信号，避免整页垃圾文案进模型
SIGNAL_HINT = re.compile(r"(生肖|特码|一肖|二肖|三肖|四肖|五肖|六肖|七肖|八肖|九肖|平特)")


async def _fetch_text_playwright(url: str) -> str:
    from app.scrapers.browser import fetch_page_text

    return await fetch_page_text(url, wait_ms=2500)


async def _fetch_frames_concat(url: str) -> str:
    from app.scrapers.browser import fetch_page_text

    return await fetch_page_text(url, wait_ms=3500, include_frames=True)


def _chunks_for_period(text: str, period: int) -> list[str]:
    pattern = re.compile(rf"{period}期.*?(?=\d{{1,4}}期|$)", re.S)
    return [m.group(0).strip() for m in pattern.finditer(text) if m.group(0).strip()]


def _parse_and_store(period: int, site_code: str, url: str, text: str) -> int:
    """只存当期相关段落里的生肖列表，不是整站全文打分。"""
    chunks = _chunks_for_period(text, period)
    if not chunks:
        if str(period) in text or f"{period}期" in text:
            chunks = [text[:4000]]
        elif SIGNAL_HINT.search(text):
            chunks = [text[:2000]]
        else:
            return 0

    saved = 0
    for chunk in chunks[:12]:
        if not SIGNAL_HINT.search(chunk) and f"{period}期" not in chunk:
            continue
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


async def scrape_tip_site(period: int, site: TipSite) -> dict[str, Any]:
    total = 0
    used: list[str] = []
    for url in all_tip_fetch_urls(site):
        try:
            if site.prefer_frames or "dinggeshui" in url:
                text = await _fetch_frames_concat(url)
                if len(text.strip()) < 40:
                    text = await _fetch_text_playwright(url)
            else:
                text = await _fetch_text_playwright(url)
                if "七肖" not in text and "一肖" not in text and "九肖" not in text:
                    text = await _fetch_frames_concat(url)
            n = _parse_and_store(period, site.code, url, text)
            total += n
            used.append(url)
            if n > 0:
                break
        except Exception as exc:
            used.append(f"{url}#err:{type(exc).__name__}:{exc}")
    return {
        "site": site.code,
        "name": site.name,
        "saved": total,
        "urls": used,
        "note": site.note,
    }


async def sync_tips(period: int) -> dict[str, Any]:
    delete_tips_for_period(period)
    results: dict[str, Any] = {"period": period, "sites": []}
    for site in enabled_tip_sites():
        item = await scrape_tip_site(period, site)
        results["sites"].append(item)
        results[site.code] = item  # 兼容旧字段名访问
    results["saved_total"] = sum(int(s.get("saved") or 0) for s in results["sites"])
    return results


def tip_scores_for_period(period: int, tips: list[dict[str, Any]]) -> dict[str, float]:
    scores = {z: 0.0 for z in ZODIAC_ORDER}
    for tip in tips:
        zodiacs = tip.get("parsed_zodiacs") or []
        if isinstance(zodiacs, str):
            continue
        tip_type = tip.get("tip_type") or ""
        w = TIP_WEIGHT.get(tip_type, 0.15)
        focus = 1.0 / max(len(zodiacs), 1)
        for z in zodiacs:
            if z in scores:
                scores[z] += w * focus
    return scores
