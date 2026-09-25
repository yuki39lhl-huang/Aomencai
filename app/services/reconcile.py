"""开奖后自动对账：系统推荐命中 + 各站 tip 命中。"""
from __future__ import annotations

from typing import Any, Literal

from app.config import settings
from app.repositories import (
    get_draw,
    list_recommends_pending_hit,
    list_tip_periods_for_site_hits,
    list_tips,
    site_hit_stats,
    update_recommend_hit,
    upsert_site_tip_hit,
)
from app.scrapers.tips import TIP_WEIGHT, primary_tip_for_site
from app.services.zodiac import bao_xiao_hit

PlayType = Literal["bao_xiao", "te_ma"]


def _tema_hit(zodiac: str, draw: dict[str, Any]) -> bool:
    return zodiac == draw.get("special_zodiac")


def _evaluate_zodiacs(
    zodiacs: list[str], draw: dict[str, Any], play_type: PlayType
) -> bool:
    if not zodiacs:
        return False
    if play_type == "bao_xiao":
        return any(bao_xiao_hit(z, draw, settings.lunar_year) for z in zodiacs)
    return any(_tema_hit(z, draw) for z in zodiacs)


def reconcile_recommend_period(period: int) -> list[dict[str, Any]]:
    draw = get_draw(period)
    if not draw:
        return []
    from app.repositories import get_recommends_for_period

    out: list[dict[str, Any]] = []
    for row in get_recommends_for_period(period):
        play = row["play_type"]
        zodiac = row["zodiac"]
        if play == "bao_xiao":
            hit = bao_xiao_hit(zodiac, draw, settings.lunar_year)
        else:
            hit = _tema_hit(zodiac, draw)
        update_recommend_hit(period, play, hit)
        out.append({"period": period, "play_type": play, "zodiac": zodiac, "hit": hit})
    return out


def reconcile_site_tips_period(period: int) -> list[dict[str, Any]]:
    draw = get_draw(period)
    if not draw:
        return []
    tips = list_tips(period)
    by_site: dict[str, list[dict[str, Any]]] = {}
    for tip in tips:
        by_site.setdefault(tip["site_code"], []).append(tip)

    out: list[dict[str, Any]] = []
    for site_code, items in by_site.items():
        primary = primary_tip_for_site(items)
        if not primary:
            continue
        zodiacs = list(primary.get("parsed_zodiacs") or [])
        tip_type = primary.get("tip_type")
        # 与系统「只荐一肖」对齐：取主推最前 1 个生肖计命中，避免七肖虚高
        focus = zodiacs[:1]
        for play in ("bao_xiao", "te_ma"):
            hit = _evaluate_zodiacs(focus, draw, play)  # type: ignore[arg-type]
            upsert_site_tip_hit(
                period=period,
                site_code=site_code,
                play_type=play,
                hit=hit,
                primary_zodiacs=focus,
                tip_type=tip_type,
            )
            out.append(
                {
                    "period": period,
                    "site_code": site_code,
                    "play_type": play,
                    "hit": hit,
                    "zodiacs": focus,
                    "tip_type": tip_type,
                }
            )
    return out


def reconcile_pending() -> dict[str, Any]:
    """回填所有待对账推荐 + 有 tip 未记命中的期。"""
    recommend_rows: list[dict[str, Any]] = []
    seen_rec: set[int] = set()
    for row in list_recommends_pending_hit():
        p = int(row["period"])
        if p in seen_rec:
            continue
        seen_rec.add(p)
        recommend_rows.extend(reconcile_recommend_period(p))

    # 已有 hit 的期若推荐被改写，也允许按最近开奖再刷一遍最近若干期
    site_rows: list[dict[str, Any]] = []
    for p in list_tip_periods_for_site_hits():
        site_rows.extend(reconcile_site_tips_period(p))

    return {
        "recommend": recommend_rows,
        "site_tips": site_rows,
        "recommend_periods": sorted(seen_rec),
        "site_periods": sorted({r["period"] for r in site_rows}),
    }


def site_weights_for_period(
    play_type: PlayType, target_period: int
) -> dict[str, float]:
    """根据 target_period 之前近 N 期命中率，给出站点权重（无样本≈1）。"""
    window = settings.site_hit_window
    stats = site_hit_stats(play_type, before_period=target_period, window=window)
    expected = (
        settings.expected_hit_bao if play_type == "bao_xiao" else settings.expected_hit_tema
    )
    floor = settings.site_weight_floor
    ceil = settings.site_weight_ceil
    prior_n = 4.0  # 先验样本量，中心落在 expected，避免小样本全被顶到上限
    out: dict[str, float] = {}
    for code, st in stats.items():
        total = int(st["total"])
        hits = int(st["hits"])
        if total <= 0:
            out[code] = 1.0
            continue
        rate = (hits + expected * prior_n) / (total + prior_n)
        weight = rate / max(expected, 1e-6)
        out[code] = max(floor, min(ceil, round(weight, 4)))
    return out


def hit_summary(limit: int = 16) -> dict[str, Any]:
    from app.repositories import list_recent_recommend_hits

    rows = list_recent_recommend_hits(limit=limit * 2)
    by_play: dict[str, dict[str, int]] = {
        "bao_xiao": {"hit": 0, "miss": 0, "pending": 0},
        "te_ma": {"hit": 0, "miss": 0, "pending": 0},
    }
    items: list[dict[str, Any]] = []
    for r in rows:
        play = r["play_type"]
        hit = r.get("hit")
        if play in by_play:
            if hit is None:
                by_play[play]["pending"] += 1
            elif int(hit) == 1:
                by_play[play]["hit"] += 1
            else:
                by_play[play]["miss"] += 1
        items.append(
            {
                "period": r["period"],
                "play_type": play,
                "zodiac": r["zodiac"],
                "hit": None if hit is None else bool(int(hit)),
                "special_zodiac": r.get("special_zodiac"),
            }
        )
    return {"by_play": by_play, "items": items[:limit], "tip_weights": TIP_WEIGHT}
