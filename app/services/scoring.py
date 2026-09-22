from __future__ import annotations

from typing import Any, Literal

from app.config import settings
from app.repositories import get_recommends_for_period, list_draws_asc, list_tips, upsert_recommend
from app.scrapers.tips import tip_scores_for_period
from app.services.zodiac import ZODIAC_ORDER, bao_xiao_hit

PlayType = Literal["bao_xiao", "te_ma"]


def _omit_bao(draws: list[dict[str, Any]]) -> dict[str, int]:
    """包肖遗漏：平码+特码都未出现该生肖的连续期数。"""
    omit = {z: 0 for z in ZODIAC_ORDER}
    for z in ZODIAC_ORDER:
        count = 0
        for row in reversed(draws):
            if bao_xiao_hit(z, row, settings.lunar_year):
                break
            count += 1
        else:
            count = len(draws)
        omit[z] = count
    return omit


def _hot_bao(draws: list[dict[str, Any]], window: int) -> dict[str, int]:
    """包肖热度：近 N 期中，该生肖至少出现一次（平或特）的期数。"""
    recent = draws[-window:] if window > 0 else draws
    hot = {z: 0 for z in ZODIAC_ORDER}
    for row in recent:
        for z in ZODIAC_ORDER:
            if bao_xiao_hit(z, row, settings.lunar_year):
                hot[z] += 1
    return hot


def _omit_tema(draws: list[dict[str, Any]]) -> dict[str, int]:
    """特码生肖遗漏：特码未开该生肖的连续期数。"""
    omit = {z: 0 for z in ZODIAC_ORDER}
    for z in ZODIAC_ORDER:
        count = 0
        for row in reversed(draws):
            if row["special_zodiac"] == z:
                break
            count += 1
        else:
            count = len(draws)
        omit[z] = count
    return omit


def _hot_tema(draws: list[dict[str, Any]], window: int) -> dict[str, int]:
    """特码生肖热度：近 N 期特码开出该生肖的次数。"""
    recent = draws[-window:] if window > 0 else draws
    hot = {z: 0 for z in ZODIAC_ORDER}
    for row in recent:
        z = row["special_zodiac"]
        if z in hot:
            hot[z] += 1
    return hot


def _normalize(values: dict[str, float]) -> dict[str, float]:
    mx = max(values.values()) if values else 0.0
    if mx <= 0:
        return {k: 0.0 for k in values}
    return {k: float(v) / mx for k, v in values.items()}


def _score_one(
    *,
    play_type: PlayType,
    target_period: int,
    latest: int,
    history: list[dict[str, Any]],
    tip_raw: dict[str, float],
    tip_count: int,
) -> dict[str, Any]:
    if play_type == "bao_xiao":
        omit = _omit_bao(history)
        hot = _hot_bao(history, settings.hot_window)
        mode_label = "包肖"
        hit_rule = "平码或特码任一开出该生肖即中"
        reason_omit = "包肖遗漏 {n} 期（7码都未出该肖）"
        reason_hot = "近{w}期包肖出现 {n} 次"
    else:
        omit = _omit_tema(history)
        hot = _hot_tema(history, settings.hot_window)
        mode_label = "特码生肖"
        hit_rule = "仅特码开出该生肖才算中"
        reason_omit = "特码生肖遗漏 {n} 期"
        reason_hot = "近{w}期特码出现 {n} 次"

    omit_n = _normalize({k: float(v) for k, v in omit.items()})
    hot_n = _normalize({k: float(v) for k, v in hot.items()})
    tip_n = _normalize(tip_raw)

    totals: dict[str, float] = {}
    detail_per: dict[str, Any] = {}
    for z in ZODIAC_ORDER:
        total = (
            settings.weight_omit * omit_n[z]
            + settings.weight_hot * hot_n[z]
            + settings.weight_tip * tip_n[z]
        )
        totals[z] = total
        detail_per[z] = {
            "omit": omit[z],
            "omit_score": round(omit_n[z], 4),
            "hot": hot[z],
            "hot_score": round(hot_n[z], 4),
            "tip_raw": round(tip_raw[z], 4),
            "tip_score": round(tip_n[z], 4),
            "total": round(total, 4),
        }

    winner = max(
        ZODIAC_ORDER,
        key=lambda z: (totals[z], omit[z], -ZODIAC_ORDER.index(z)),
    )

    store_detail = {
        "mode": play_type,
        "mode_label": mode_label,
        "hit_rule": hit_rule,
        "weights": {
            "omit": settings.weight_omit,
            "hot": settings.weight_hot,
            "tip": settings.weight_tip,
            "hot_window": settings.hot_window,
        },
        "winner_detail": detail_per[winner],
        "tip_count": tip_count,
        "history_count": len(history),
        "based_on_latest_draw": latest,
        "reasons": [
            reason_omit.format(n=omit[winner]),
            reason_hot.format(w=settings.hot_window, n=hot[winner]),
            f"站点推荐加权分 {round(tip_raw[winner], 4)}（共{tip_count}条）",
        ],
    }
    upsert_recommend(target_period, play_type, winner, totals[winner], store_detail)
    return {
        "period": target_period,
        "play_type": play_type,
        "mode_label": mode_label,
        "hit_rule": hit_rule,
        "zodiac": winner,
        "score": round(totals[winner], 4),
        "winner_detail": detail_per[winner],
        "score_detail": store_detail,
    }


def score_for_period(target_period: int) -> dict[str, Any]:
    """同时计算包肖 + 特码生肖两套推荐。"""
    draws = list_draws_asc()
    if not draws:
        raise ValueError("暂无开奖数据，请先刷新抓取历史")

    latest = draws[-1]["period"]
    history = [d for d in draws if d["period"] < target_period]
    if not history:
        history = draws

    tips = list_tips(target_period)
    tip_raw = tip_scores_for_period(target_period, tips)

    bao = _score_one(
        play_type="bao_xiao",
        target_period=target_period,
        latest=latest,
        history=history,
        tip_raw=tip_raw,
        tip_count=len(tips),
    )
    tema = _score_one(
        play_type="te_ma",
        target_period=target_period,
        latest=latest,
        history=history,
        tip_raw=tip_raw,
        tip_count=len(tips),
    )
    return {
        "period": target_period,
        "based_on_latest_draw": latest,
        "bao_xiao": bao,
        "te_ma": tema,
    }


def latest_recommendation() -> dict[str, Any] | None:
    from app.repositories import latest_draw, latest_recommend_period

    draw = latest_draw()
    if not draw:
        return None
    period = int(draw["period"]) + 1
    rows = get_recommends_for_period(period)
    if not rows:
        p = latest_recommend_period()
        if p is None:
            return None
        rows = get_recommends_for_period(p)
        period = p
    by_type = {r["play_type"]: r for r in rows}
    return {
        "period": period,
        "bao_xiao": by_type.get("bao_xiao"),
        "te_ma": by_type.get("te_ma"),
    }
