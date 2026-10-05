from __future__ import annotations

import re
from typing import Any

from app.repositories import delete_tips_for_period, insert_site_tip
from app.services.zodiac import ZODIAC_ORDER
from app.sites import TipSite, all_tip_fetch_urls, enabled_tip_sites

_XIAO_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ZODIAC_CHARS = set("鼠牛虎兔龙蛇马羊猴鸡狗猪")
_LABEL_RE = re.compile(r"([一二三四五六七八九])肖")


def _chunks_for_period(text: str, period: int) -> list[str]:
    pattern = re.compile(rf"{period}期.*?(?=\d{{1,4}}期|$)", re.S)
    return [m.group(0).strip() for m in pattern.finditer(text) if m.group(0).strip()]


def _scope_for_period(text: str, period: int) -> str:
    """只看当期期号后面的段落，避免把别的期或整页广告算进来。"""
    chunks = _chunks_for_period(text, period)
    if chunks:
        return "\n".join(chunks[:12])
    idx = text.find(f"{period}期")
    if idx < 0:
        return ""
    return text[idx : idx + 4000]


def _is_sep(ch: str) -> bool:
    if ch.isspace() or ch.isascii():
        return True
    if ch in "〖〗【】[]()（）:：、，,。·.✔㊣+*/|_-—~～!！?？\"'「」『』《》<>":
        return True
    if "\u2460" <= ch <= "\u2473" or "\u2776" <= ch <= "\u277f":
        return True
    return False


def _read_zodiac_run(text: str, start: int) -> list[str]:
    """从肖标签后读取连续生肖。中间只允许标点和「一码」「独肖」，广告词会把名单截断。"""
    i = start
    n = len(text)
    zodiacs: list[str] = []
    while i < n and not zodiacs:
        if text.startswith("一码", i) or text.startswith("独肖", i):
            i += 2
            continue
        ch = text[i]
        if ch in _ZODIAC_CHARS:
            break
        if _is_sep(ch):
            i += 1
            continue
        return []
    while i < n:
        ch = text[i]
        if ch in _ZODIAC_CHARS:
            zodiacs.append(ch)
            i += 1
            continue
        if not _is_sep(ch):
            break
        j = i + 1
        while j < n and _is_sep(text[j]):
            j += 1
        if j < n and text[j] in _ZODIAC_CHARS:
            i = j
            continue
        break
    return zodiacs


def parse_xiao_runs(text: str) -> list[dict[str, Any]]:
    """只保留「N肖」后面个数正好相等的生肖串。"""
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, tuple[str, ...]]] = set()
    for m in _LABEL_RE.finditer(text or ""):
        count = _XIAO_NUM[m.group(1)]
        zodiacs = _read_zodiac_run(text, m.end())
        if len(zodiacs) != count or len(set(zodiacs)) != count:
            continue
        key = (count, tuple(zodiacs))
        if key in seen:
            continue
        seen.add(key)
        label = f"{m.group(1)}肖"
        out.append(
            {
                "strategy": "xiao_line",
                "raw": text[m.start() : m.end() + 40][:500],
                "zodiacs": zodiacs,
                "tip_type": label,
                "count": count,
            }
        )
    return out


def _is_prefix(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    return len(short) < len(long) and long[: len(short)] == short


def scope_for_xiao(count: int) -> str:
    return "te_ma" if count <= 3 else "bao_xiao"


def select_ladder_tips(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一条由短到长的阶梯只留一档：特码留最短，包肖留最长。"""
    uniq: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in items:
        zodiacs = tuple(item.get("zodiacs") or [])
        count = int(item.get("count") or len(zodiacs))
        if not zodiacs or count != len(zodiacs):
            continue
        uniq[zodiacs] = {**item, "zodiacs": list(zodiacs), "count": count}
    rows = list(uniq.values())
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    seqs = [tuple(row["zodiacs"]) for row in rows]
    for i, left in enumerate(seqs):
        for j in range(i + 1, len(seqs)):
            right = seqs[j]
            if _is_prefix(left, right) or _is_prefix(right, left):
                union(i, j)

    groups: dict[int, list[dict[str, Any]]] = {}
    for i, row in enumerate(rows):
        groups.setdefault(find(i), []).append(row)

    kept: list[dict[str, Any]] = []
    for group in groups.values():
        short = [row for row in group if row["count"] <= 3]
        long = [row for row in group if row["count"] >= 4]
        if short:
            kept.append(min(short, key=lambda row: row["count"]))
        if long:
            kept.append(max(long, key=lambda row: row["count"]))
    for row in kept:
        row["play_scope"] = scope_for_xiao(int(row["count"]))
    return kept


def extract_candidates(text: str, period: int) -> list[dict[str, Any]]:
    """当期段落里的肖名单，阶梯合并后入库。"""
    scope = _scope_for_period(text, period)
    if not scope:
        return []
    return select_ladder_tips(parse_xiao_runs(scope))


def play_scope_for_tip(raw: str, tip_type: str | None, zodiacs: list[str]) -> str | None:
    """一肖到三肖归特码，四肖到九肖归包肖。个数对不上的不参与。"""
    parsed = parse_xiao_runs(raw or "")
    if len(parsed) == 1:
        return scope_for_xiao(int(parsed[0]["count"]))
    label = tip_type or ""
    count = _XIAO_NUM.get(label[:1])
    if count and len(zodiacs or []) == count:
        return scope_for_xiao(count)
    return None


def collapse_site_tips(tips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按站点把已入库原文重新收成阶梯各一档。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for tip in tips:
        raw = str(tip.get("raw_text") or tip.get("raw") or "")
        site = str(tip.get("site_code") or "")
        grouped.setdefault(site, []).extend(parse_xiao_runs(raw))
    kept: list[dict[str, Any]] = []
    for site, items in grouped.items():
        for item in select_ladder_tips(items):
            kept.append({**item, "site_code": site})
    return kept


def contributing_tips(tips: list[dict[str, Any]], play_type: str) -> list[dict[str, Any]]:
    """打分用的资料：各站阶梯收档后，只留该玩法的那一档。"""
    return [tip for tip in collapse_site_tips(tips) if tip.get("play_scope") == play_type]


def _store_candidates(
    period: int, site_code: str, url: str, candidates: list[dict[str, Any]]
) -> tuple[int, list[str]]:
    saved = 0
    strategies: list[str] = []
    picked: list[dict[str, Any]] = []
    per_scope = {"bao_xiao": 0, "te_ma": 0}
    for item in candidates:
        zodiacs = item.get("zodiacs") or []
        if not zodiacs:
            continue
        scope = item.get("play_scope") or play_scope_for_tip(
            str(item.get("raw") or ""), item.get("tip_type"), zodiacs
        )
        if scope not in per_scope or per_scope[scope] >= 8:
            continue
        per_scope[scope] += 1
        picked.append({**item, "play_scope": scope})
    for item in picked:
        zodiacs = item.get("zodiacs") or []
        strategy = str(item.get("strategy") or "unknown")
        raw = f"[{strategy}] {item.get('raw') or ''}"
        insert_site_tip(
            period=period,
            site_code=site_code,
            page_url=url,
            raw_text=raw[:5000],
            parsed_zodiacs=zodiacs,
            tip_type=item.get("tip_type"),
            play_scope=item.get("play_scope"),
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
    """阶梯收档后的资料分。每个生肖只分到该档名单的一份，不再按肖数再打一层折。"""
    weights = site_weights or {}
    scores = {z: 0.0 for z in ZODIAC_ORDER}
    for tip in contributing_tips(tips, play_type):
        zodiacs = list(tip.get("zodiacs") or [])
        if not zodiacs:
            continue
        w = float(weights.get(str(tip.get("site_code") or ""), 1.0))
        if w <= 0:
            continue
        focus = 1.0 / len(zodiacs)
        for zodiac in zodiacs:
            if zodiac in scores:
                scores[zodiac] += w * focus
    return scores


def primary_tip_for_site(
    tips: list[dict[str, Any]], *, play_type: str | None = None
) -> dict[str, Any] | None:
    """每站取收档后最聚焦的一条作为对账主推。"""
    rows = collapse_site_tips(tips)
    if play_type:
        rows = [tip for tip in rows if tip.get("play_scope") == play_type]
    if not rows:
        return None
    picked = sorted(rows, key=lambda tip: (int(tip.get("count") or 99), tip.get("tip_type") or ""))[0]
    zodiacs = list(picked.get("zodiacs") or [])
    return {**picked, "parsed_zodiacs": zodiacs, "zodiacs": zodiacs}
