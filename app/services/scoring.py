from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from app.config import settings
from app.repositories import (
    get_recommends_for_period,
    list_draws_asc,
    list_locked_bao_missing_lian,
    list_tips,
    upsert_recommend,
)
from app.scrapers.tips import contributing_tips, tip_scores_for_period
from app.services.zodiac import ZODIAC_ORDER, bao_xiao_hit, lunar_year_for, year_zodiac

_ZERO_TIPS = {z: 0.0 for z in ZODIAC_ORDER}

PlayType = Literal["bao_xiao", "te_ma"]


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value[:10]:
        return date.fromisoformat(value[:10])
    return None


def year_zodiac_for_period(target_period: int, draws: list[dict[str, Any]]) -> str:
    """这一期开奖日所属生肖年里占 5 个号的那一只。还没开奖就用上一期的次日。"""
    for row in draws:
        if int(row["period"]) == target_period:
            day = _as_date(row.get("draw_date"))
            if day:
                return year_zodiac(lunar_year_for(day))
    prior = [row for row in draws if int(row["period"]) < target_period]
    if prior:
        day = _as_date(prior[-1].get("draw_date"))
        if day:
            return year_zodiac(lunar_year_for(day + timedelta(days=1)))
    return year_zodiac(lunar_year_for(None))


def _omit_bao(draws: list[dict[str, Any]]) -> dict[str, int]:
    """包肖遗漏：平码+特码都未出现该生肖的连续期数。"""
    omit = {z: 0 for z in ZODIAC_ORDER}
    for z in ZODIAC_ORDER:
        count = 0
        for row in reversed(draws):
            if bao_xiao_hit(z, row):
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
            if bao_xiao_hit(z, row):
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


def _gap_component(values: dict[str, int], *, center: int, half_width: int) -> dict[str, float]:
    """越接近典型间隔分越高，过冷和刚出过都降分。"""
    if not values or half_width <= 0:
        return {k: 0.0 for k in values}
    out: dict[str, float] = {}
    for key, value in values.items():
        dist = abs(float(value) - center) / half_width
        out[key] = 1.0 / (1.0 + dist)
    return out


def _scaled_component(
    values: dict[str, int], *, min_lead: int, full_at: int
) -> dict[str, float]:
    """领先不够则整项为 0；够了按固定刻度给分，不把最大值自动当成满分。"""
    if not values or full_at <= 0:
        return {k: 0.0 for k in values}
    ordered = sorted((float(v) for v in values.values()), reverse=True)
    top = ordered[0]
    second = ordered[1] if len(ordered) > 1 else 0.0
    if top - second < min_lead:
        return {k: 0.0 for k in values}
    return {k: min(float(v) / full_at, 1.0) for k, v in values.items()}


def _score_one(
    *,
    play_type: PlayType,
    target_period: int,
    latest: int,
    history: list[dict[str, Any]],
    tip_raw: dict[str, float],
    tip_count: int,
    site_weights: dict[str, float] | None = None,
    anchor: str | None = None,
) -> dict[str, Any]:
    if play_type == "bao_xiao":
        omit = _omit_bao(history)
        hot = _hot_bao(history, settings.hot_window)
        mode_label = "包肖"
        hit_rule = "平码或特码任一开出该生肖即中"
        omit_center = settings.bao_omit_center
        omit_half = settings.bao_omit_half
        hot_full = settings.hot_window
        tip_weight = settings.weight_tip
    else:
        omit = _omit_tema(history)
        hot = _hot_tema(history, settings.hot_window)
        mode_label = "特码生肖"
        hit_rule = "仅特码开出该生肖才算中"
        omit_center = settings.tema_omit_center
        omit_half = settings.tema_omit_half
        hot_full = settings.tema_hot_full
        tip_weight = 0.0

    omit_n = _gap_component(omit, center=omit_center, half_width=omit_half)
    hot_n = _scaled_component(hot, min_lead=settings.score_min_lead, full_at=hot_full)
    tip_n = _normalize(tip_raw) if tip_weight > 0 else {z: 0.0 for z in ZODIAC_ORDER}

    totals: dict[str, float] = {}
    detail_per: dict[str, Any] = {}
    for z in ZODIAC_ORDER:
        total = (
            settings.weight_omit * omit_n[z]
            + settings.weight_hot * hot_n[z]
            + tip_weight * tip_n[z]
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

    ranked = sorted(
        ZODIAC_ORDER,
        key=lambda z: (totals[z], -abs(omit[z] - omit_center), -ZODIAC_ORDER.index(z)),
        reverse=True,
    )
    formula_top = ranked[0]
    # 单肖固定为当年肖。旧分只决定连肖里当年肖以外的名次，特码仍走上面的旧分。
    if play_type == "bao_xiao" and anchor in ZODIAC_ORDER:
        ranked = [anchor, *[z for z in ranked if z != anchor]]
    winner = ranked[0]
    place_rows = [
        {
            "place": label,
            "zodiac": z,
            "score": round(totals[z], 4),
            "omit": omit[z],
            "hot": hot[z],
        }
        for label, z in zip(_PLACE_LABELS, ranked)
    ]

    existing = next(
        (
            row
            for row in get_recommends_for_period(target_period)
            if row["play_type"] == play_type and row.get("hit") is not None
        ),
        None,
    )
    if existing:
        stored_rank = (existing.get("score_detail") or {}).get("ranking") or []
        return {
            "period": target_period,
            "play_type": play_type,
            "mode_label": mode_label,
            "hit_rule": hit_rule,
            "zodiac": existing["zodiac"],
            "score": round(float(existing["score"]), 4),
            "score_detail": existing.get("score_detail") or {},
            "ranking": stored_rank or place_rows,
            "locked": True,
        }

    store_detail = {
        "mode": play_type,
        "mode_label": mode_label,
        "hit_rule": hit_rule,
        "weights": {
            "omit": settings.weight_omit,
            "hot": settings.weight_hot,
            "tip": tip_weight,
            "hot_window": settings.hot_window,
            "min_lead": settings.score_min_lead,
            "omit_center": omit_center,
            "omit_half": omit_half,
            "hot_full": hot_full,
        },
        "site_weights": site_weights or {},
        "winner_detail": detail_per[winner],
        "ranking": place_rows,
        "tip_count": tip_count,
        "history_count": len(history),
        "based_on_latest_draw": latest,
        "year_zodiac": anchor if play_type == "bao_xiao" else None,
        "formula_top": formula_top if play_type == "bao_xiao" else None,
        "reasons": _reasons(
            play_type=play_type,
            mode_label=mode_label,
            winner=winner,
            omit=omit,
            hot=hot,
            omit_n=omit_n,
            hot_n=hot_n,
            tip_raw=tip_raw,
            tip_count=tip_count,
            omit_center=omit_center,
            formula_top=formula_top,
        ),
    }
    upsert_recommend(target_period, play_type, winner, totals[winner], store_detail)
    return {
        "period": target_period,
        "play_type": play_type,
        "mode_label": mode_label,
        "hit_rule": hit_rule,
        "zodiac": winner,
        "score": round(totals[winner], 4),
        "score_detail": store_detail,
        "ranking": place_rows,
    }


_PLACE_LABELS = ("冠军", "亚军", "季军", "第四", "第五")
_LIAN = (("lian3", 3, "三连肖"), ("lian5", 5, "五连肖"))


def _score_lian(
    *,
    target_period: int,
    bao: dict[str, Any],
    existing: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """连肖取单肖排名的前 3 / 前 5。单肖已把当年肖放在第一，所以组里必有当年肖。"""
    out: dict[str, Any] = {}
    ranking = bao.get("ranking") or []
    for play, size, label in _LIAN:
        row = existing.get(play)
        if row and (row.get("hit") is not None or bao.get("locked")):
            out[play] = {**row, "mode_label": label, "locked": row.get("hit") is not None}
            continue
        if len(ranking) < size:
            out[play] = None
            continue
        if bao.get("locked") and ranking[0]["zodiac"] != bao.get("zodiac"):
            out[play] = None
            continue
        if bao.get("locked") and play == "lian5":
            stored3 = (existing.get("lian3") or {}).get("zodiacs") or []
            if stored3 and [p["zodiac"] for p in ranking[:3]] != list(stored3):
                out[play] = None
                continue
        group = ranking[:size]
        zodiacs = [p["zodiac"] for p in group]
        score = round(sum(p["score"] for p in group) / size, 4)
        rest = "、".join(zodiacs[1:])
        detail = {
            "mode": play,
            "mode_label": label,
            "hit_rule": f"当年肖在第一位，其余按旧分排。{size}个生肖都出现在7个号码里才算中",
            "places": group,
            "based_on_latest_draw": (bao.get("score_detail") or {}).get("based_on_latest_draw"),
            "reasons": [f"第一只是当年肖「{zodiacs[0]}」，其余按旧公式：{rest}。"],
        }
        upsert_recommend(target_period, play, zodiacs[0], score, detail, zodiacs=zodiacs)
        out[play] = {
            "period": target_period,
            "play_type": play,
            "mode_label": label,
            "zodiac": zodiacs[0],
            "zodiacs": zodiacs,
            "score": score,
            "score_detail": detail,
        }
    return out


def _compute_bao_places(target_period: int) -> list[dict[str, Any]]:
    """按旧分重算名次，当年肖放回第一。只用于补写缺的连肖，不改已锁定的单肖。"""
    from app.services.reconcile import site_weights_for_period

    draws = list_draws_asc()
    history = [d for d in draws if int(d["period"]) < target_period]
    if not history:
        return []
    tips = list_tips(target_period)
    weights = site_weights_for_period("bao_xiao", target_period)
    tip_raw = tip_scores_for_period(
        target_period, tips, play_type="bao_xiao", site_weights=weights
    )
    omit = _omit_bao(history)
    hot = _hot_bao(history, settings.hot_window)
    center = settings.bao_omit_center
    omit_n = _gap_component(omit, center=center, half_width=settings.bao_omit_half)
    hot_n = _scaled_component(hot, min_lead=settings.score_min_lead, full_at=settings.hot_window)
    tip_n = _normalize(tip_raw)
    totals = {
        z: settings.weight_omit * omit_n[z] + settings.weight_hot * hot_n[z] + settings.weight_tip * tip_n[z]
        for z in ZODIAC_ORDER
    }
    ranked = sorted(
        ZODIAC_ORDER,
        key=lambda z: (totals[z], -abs(omit[z] - center), -ZODIAC_ORDER.index(z)),
        reverse=True,
    )
    anchor = year_zodiac_for_period(target_period, draws)
    if anchor in ranked:
        ranked = [anchor, *[z for z in ranked if z != anchor]]
    return [
        {
            "place": label,
            "zodiac": z,
            "score": round(totals[z], 4),
            "omit": omit[z],
            "hot": hot[z],
        }
        for label, z in zip(_PLACE_LABELS, ranked)
    ]


def _write_lian(period: int, size: int, places: list[dict[str, Any]]) -> None:
    group = places[:size]
    zodiacs = [p["zodiac"] for p in group]
    play = "lian3" if size == 3 else "lian5"
    label = "三连肖" if size == 3 else "五连肖"
    score = round(sum(float(p["score"]) for p in group) / size, 4)
    detail = {
        "mode": play,
        "mode_label": label,
        "hit_rule": f"{size}个生肖都出现在7个号码里才算中",
        "places": group,
        "backfill": "locked_bao",
    }
    upsert_recommend(period, play, zodiacs[0], score, detail, zodiacs=zodiacs)


def backfill_missing_lian() -> dict[str, Any]:
    """单肖已有中没中、却缺连肖时补写一次。第一名必须还是这只已锁定的肖。"""
    wrote: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in list_locked_bao_missing_lian():
        period = int(row["period"])
        detail = row.get("score_detail") or {}
        places = list(detail.get("ranking") or [])
        if not places or places[0].get("zodiac") != row["zodiac"]:
            places = _compute_bao_places(period)
        if not places or places[0].get("zodiac") != row["zodiac"]:
            skipped.append({"period": period, "reason": "排名和已锁定的单肖不一致"})
            continue
        stored3 = list(row.get("lian3_zodiacs") or [])
        if not stored3:
            _write_lian(period, 3, places)
            wrote.append({"period": period, "play_type": "lian3", "zodiacs": [p["zodiac"] for p in places[:3]]})
            stored3 = [p["zodiac"] for p in places[:3]]
        if row.get("lian5_period") is None:
            top3 = [p["zodiac"] for p in places[:3]]
            if stored3 != top3:
                skipped.append({"period": period, "reason": "五连肖和已记下的三连肖对不上"})
            else:
                _write_lian(period, 5, places)
                wrote.append({"period": period, "play_type": "lian5", "zodiacs": [p["zodiac"] for p in places[:5]]})
    return {"wrote": wrote, "skipped": skipped}


def _reasons(
    *,
    play_type: str,
    mode_label: str,
    winner: str,
    omit: dict[str, int],
    hot: dict[str, int],
    omit_n: dict[str, float],
    hot_n: dict[str, float],
    tip_raw: dict[str, float],
    tip_count: int,
    omit_center: int,
    formula_top: str,
) -> list[str]:
    if play_type == "bao_xiao":
        fixed = (
            f"单肖固定为当年肖「{winner}」。这一只占 5 个号，大约 55%；"
            "其余每只 4 个号，大约 47%。"
        )
        if formula_top == winner:
            fixed += "旧公式第一名也是这一只。"
        else:
            fixed += f"旧公式第一名是「{formula_top}」，只用来排连肖里当年肖以外的位置。"
        return [
            fixed,
            "遗漏、热度和资料仍会计算，但不改单肖。",
            f"包肖资料 {tip_count} 条，当年肖加权分 {round(tip_raw[winner], 4)}。",
        ]
    lead = settings.score_min_lead
    omit_line = (
        f"{mode_label}遗漏 {omit[winner]} 期，越接近 {omit_center} 期分越高，"
        f"得分 {round(omit_n[winner], 2)}"
    )
    if max(hot_n.values() or [0]) <= 0:
        hot_line = (
            f"近{settings.hot_window}期热度领先不足 {lead} 次，这项不计分"
            f"（当前 {hot[winner]} 次）"
        )
    else:
        hot_line = f"近{settings.hot_window}期出现 {hot[winner]} 次，得分 {round(hot_n[winner], 2)}"
    if play_type == "te_ma":
        tip_line = f"特码资料 {tip_count} 条，不计入排名"
    else:
        tip_line = f"{mode_label}资料 {tip_count} 条，加权分 {round(tip_raw[winner], 4)}"
    return [omit_line, hot_line, tip_line]


def _count_scoped_tips(tips: list[dict[str, Any]], play_type: str) -> int:
    return len(contributing_tips(tips, play_type))


def score_for_period(target_period: int) -> dict[str, Any]:
    """同时计算包肖 + 特码生肖两套推荐。"""
    from app.services.reconcile import site_weights_for_period

    draws = list_draws_asc()
    if not draws:
        raise ValueError("暂无开奖数据，请先刷新抓取历史")

    latest = draws[-1]["period"]
    history = [d for d in draws if d["period"] < target_period]
    if not history:
        history = draws

    tips = list_tips(target_period)
    bao_tip_count = _count_scoped_tips(tips, "bao_xiao")
    tema_tip_count = _count_scoped_tips(tips, "te_ma")
    bao_site_w = site_weights_for_period("bao_xiao", target_period)
    tip_raw_bao = tip_scores_for_period(
        target_period, tips, play_type="bao_xiao", site_weights=bao_site_w
    )
    tip_raw_tema = dict(_ZERO_TIPS)

    anchor = year_zodiac_for_period(target_period, draws)
    bao = _score_one(
        play_type="bao_xiao",
        target_period=target_period,
        latest=latest,
        history=history,
        tip_raw=tip_raw_bao,
        tip_count=bao_tip_count,
        site_weights=bao_site_w,
        anchor=anchor,
    )
    tema = _score_one(
        play_type="te_ma",
        target_period=target_period,
        latest=latest,
        history=history,
        tip_raw=tip_raw_tema,
        tip_count=tema_tip_count,
    )
    existing = {r["play_type"]: r for r in get_recommends_for_period(target_period)}
    lian = _score_lian(target_period=target_period, bao=bao, existing=existing)
    return {
        "period": target_period,
        "based_on_latest_draw": latest,
        "bao_xiao": bao,
        "lian3": lian["lian3"],
        "lian5": lian["lian5"],
        "te_ma": tema,
        "site_weights": {"bao_xiao": bao_site_w},
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
        "lian3": by_type.get("lian3"),
        "lian5": by_type.get("lian5"),
        "te_ma": by_type.get("te_ma"),
    }
