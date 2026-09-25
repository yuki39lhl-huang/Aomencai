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

SIGNAL_HINT = re.compile(r"(生肖|特码|一肖|二肖|三肖|四肖|五肖|六肖|七肖|八肖|九肖|平特)")
TIP_LINE_RE = re.compile(
    r"(?P<label>[一二三四五六七八九]肖)[^鼠牛虎兔龙蛇马羊猴鸡狗猪]{0,12}"
    r"(?P<body>[鼠牛虎兔龙蛇马羊猴鸡狗猪]+(?:[^鼠牛虎兔龙蛇马羊猴鸡狗猪]{0,4}[鼠牛虎兔龙蛇马羊猴鸡狗猪]+)*)"
)


def _chunks_for_period(text: str, period: int) -> list[str]:
    pattern = re.compile(rf"{period}期.*?(?=\d{{1,4}}期|$)", re.S)
    return [m.group(0).strip() for m in pattern.finditer(text) if m.group(0).strip()]


def _extract_period_chunks(text: str, period: int) -> list[dict[str, Any]]:
    """策略 A：按当期期号切段。"""
    chunks = _chunks_for_period(text, period)
    if not chunks and (str(period) in text or f"{period}期" in text):
        chunks = [text[:4000]]
    out: list[dict[str, Any]] = []
    for chunk in chunks[:12]:
        zodiacs = extract_zodiacs_from_text(chunk)
        if not zodiacs:
            continue
        out.append(
            {
                "strategy": "period_chunk",
                "raw": chunk[:5000],
                "zodiacs": zodiacs,
                "tip_type": tip_type_from_text(chunk),
            }
        )
    return out


def _extract_tip_lines(text: str) -> list[dict[str, Any]]:
    """策略 B：整页找「N肖 + 生肖串」行。"""
    out: list[dict[str, Any]] = []
    for m in TIP_LINE_RE.finditer(text.replace("\n", " ")):
        label = m.group("label")
        body = m.group("body")
        zodiacs = extract_zodiacs_from_text(body)
        if not zodiacs:
            continue
        out.append(
            {
                "strategy": "tip_line",
                "raw": m.group(0)[:5000],
                "zodiacs": zodiacs,
                "tip_type": label,
            }
        )
    return out[:12]


def _extract_signal_window(text: str) -> list[dict[str, Any]]:
    """策略 C：含信号词的窗口，取出现的生肖。"""
    if not SIGNAL_HINT.search(text):
        return []
    # 取含信号的片段，避免整页广告
    parts = re.split(r"[\n\r]+", text)
    windows: list[str] = []
    for i, line in enumerate(parts):
        if SIGNAL_HINT.search(line) or extract_zodiacs_from_text(line):
            chunk = "\n".join(parts[max(0, i - 1) : i + 3])
            windows.append(chunk)
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for w in windows[:20]:
        zodiacs = extract_zodiacs_from_text(w)
        if len(zodiacs) < 1:
            continue
        key = tuple(zodiacs)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "strategy": "signal_window",
                "raw": w[:5000],
                "zodiacs": zodiacs,
                "tip_type": tip_type_from_text(w),
            }
        )
    return out[:12]


def _rank_extractions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """比对：期号策略优先，其次短列表（更像一肖/二肖），再次 tip_line。"""
    priority = {"period_chunk": 0, "tip_line": 1, "signal_window": 2}

    def key(it: dict[str, Any]):
        tip = it.get("tip_type") or ""
        tip_score = TIP_WEIGHT.get(tip, 0.1)
        return (
            priority.get(it.get("strategy") or "", 9),
            -tip_score,
            len(it.get("zodiacs") or []),
        )

    return sorted(items, key=key)


def extract_candidates(text: str, period: int) -> list[dict[str, Any]]:
    """多策略抽取后合并比对。"""
    merged: list[dict[str, Any]] = []
    period_items = _extract_period_chunks(text, period)
    merged.extend(period_items)
    # tip_line / signal 优先在当期段落内比，没有当期段落才退回整页
    scope = "\n".join(_chunks_for_period(text, period)) or text
    merged.extend(_extract_tip_lines(scope))
    if not merged:
        merged.extend(_extract_signal_window(scope))
    return _rank_extractions(merged)


def _store_candidates(
    period: int, site_code: str, url: str, candidates: list[dict[str, Any]]
) -> tuple[int, list[str]]:
    saved = 0
    strategies: list[str] = []
    for item in candidates[:12]:
        zodiacs = item.get("zodiacs") or []
        if not zodiacs:
            continue
        strategy = str(item.get("strategy") or "unknown")
        raw = f"[{strategy}] {item.get('raw') or ''}"
        insert_site_tip(
            period=period,
            site_code=site_code,
            page_url=url,
            raw_text=raw[:5000],
            parsed_zodiacs=zodiacs,
            tip_type=item.get("tip_type"),
        )
        saved += 1
        if strategy not in strategies:
            strategies.append(strategy)
    return saved, strategies


async def _fetch_text(url: str, prefer_frames: bool) -> str:
    from app.scrapers.browser import fetch_page_text

    if prefer_frames:
        text = await fetch_page_text(url, wait_ms=3500, include_frames=True)
        if len(text.strip()) < 40:
            text = await fetch_page_text(url, wait_ms=2500, include_frames=False)
        return text
    text = await fetch_page_text(url, wait_ms=2500, include_frames=False)
    if "七肖" not in text and "一肖" not in text and "九肖" not in text:
        text = await fetch_page_text(url, wait_ms=3500, include_frames=True)
    return text


async def scrape_tip_site(period: int, site: TipSite) -> dict[str, Any]:
    total = 0
    used: list[str] = []
    strategies_used: list[str] = []
    prefer = site.prefer_frames or "dinggeshui" in site.code

    urls = all_tip_fetch_urls(site)
    tried_extra = False

    i = 0
    while i < len(urls):
        url = urls[i]
        i += 1
        try:
            text = await _fetch_text(url, prefer)
            candidates = extract_candidates(text, period)
            n, st = _store_candidates(period, site.code, url, candidates)
            total += n
            used.append(url)
            for s in st:
                if s not in strategies_used:
                    strategies_used.append(s)
            if n > 0:
                break
            # 主 URL 抽不到：发现子链接换源再比
            if not tried_extra:
                tried_extra = True
                from app.scrapers.browser import discover_tip_links

                extras = await discover_tip_links(url, limit=6)
                for e in extras:
                    if e not in urls:
                        urls.append(e)
        except Exception as exc:
            used.append(f"{url}#err:{type(exc).__name__}:{exc}")

    return {
        "site": site.code,
        "name": site.name,
        "saved": total,
        "urls": used,
        "strategies": strategies_used,
        "note": site.note,
    }


async def sync_tips(period: int) -> dict[str, Any]:
    delete_tips_for_period(period)
    results: dict[str, Any] = {"period": period, "sites": []}
    for site in enabled_tip_sites():
        item = await scrape_tip_site(period, site)
        results["sites"].append(item)
        results[site.code] = item
    results["saved_total"] = sum(int(s.get("saved") or 0) for s in results["sites"])
    return results


def tip_scores_for_period(
    period: int,
    tips: list[dict[str, Any]],
    *,
    play_type: str = "bao_xiao",
    site_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """按玩法拆分 tip 贡献，并乘以站点近期命中权重。"""
    weights = site_weights or {}
    scores = {z: 0.0 for z in ZODIAC_ORDER}
    for tip in tips:
        zodiacs = tip.get("parsed_zodiacs") or []
        if isinstance(zodiacs, str) or not zodiacs:
            continue
        tip_type = tip.get("tip_type") or ""
        w = TIP_WEIGHT.get(tip_type, 0.15)
        raw = tip.get("raw_text") or ""
        if raw.startswith("[period_chunk]"):
            w *= 1.15
        elif raw.startswith("[signal_window]"):
            w *= 0.85
        w *= _play_relevance(raw, tip_type, len(zodiacs), play_type)
        site_code = tip.get("site_code") or ""
        w *= float(weights.get(site_code, 1.0))
        if w <= 0:
            continue
        focus = 1.0 / max(len(zodiacs), 1)
        for z in zodiacs:
            if z in scores:
                scores[z] += w * focus
    return scores


def _play_relevance(raw: str, tip_type: str, n_zodiacs: int, play_type: str) -> float:
    """同一条 tip 对包肖 / 特码的相关度不同。"""
    if play_type == "te_ma":
        if "特码" in raw or "特肖" in raw:
            return 1.15
        if tip_type == "一肖":
            return 1.0
        if tip_type in ("二肖", "三肖") and n_zodiacs <= 3:
            return 0.75
        if tip_type in ("七肖", "八肖", "九肖") or "平特" in raw or "包肖" in raw:
            return 0.2
        return 0.4
    # bao_xiao
    if "平特" in raw or "包肖" in raw:
        return 1.15
    if tip_type in ("四肖", "五肖", "六肖", "七肖", "八肖", "九肖"):
        return 1.0
    if tip_type in ("二肖", "三肖"):
        return 0.85
    if tip_type == "一肖" or "特码" in raw:
        return 0.55
    return 0.7


def primary_tip_for_site(tips: list[dict[str, Any]]) -> dict[str, Any] | None:
    """每站取最聚焦的一条作为对账主推（类型权重大、生肖少优先）。"""
    valid = []
    for tip in tips:
        zodiacs = tip.get("parsed_zodiacs") or []
        if isinstance(zodiacs, str) or not zodiacs:
            continue
        valid.append(tip)
    if not valid:
        return None

    def key(tip: dict[str, Any]):
        tip_type = tip.get("tip_type") or ""
        zodiacs = tip.get("parsed_zodiacs") or []
        return (-TIP_WEIGHT.get(tip_type, 0.1), len(zodiacs), tip.get("id") or 0)

    return sorted(valid, key=key)[0]
