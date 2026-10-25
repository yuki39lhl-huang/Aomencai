"""滚动回测：预测第 N 期时只用更早的开奖。不写推荐，不改权重。"""
from __future__ import annotations

import math
from datetime import date, datetime, time
from itertools import combinations
from typing import Any

from app.config import settings
from app.repositories import (
    latest_backtest_snapshot,
    list_draws_asc,
    list_tips_by_period,
    save_backtest_snapshot,
)
from app.scrapers.tips import contributing_tips, tip_scores_for_period
from app.services.reconcile import site_weights_for_period
from app.services.scoring import (
    _gap_component,
    _hot_bao,
    _hot_tema,
    _normalize,
    _omit_bao,
    _omit_tema,
    _scaled_component,
)
from app.services.zodiac import ZODIAC_ORDER, bao_xiao_hit, lunar_year_for, year_zodiac, zodiac_numbers
from app.sites import enabled_tip_sites

_START = 40
_RULE = "pre_draw_21_32_year_live"
# 共识实验：热度权重两档；资料只认至少这么多个启用站同推的肖
_CONSENSUS_HOT_WEIGHTS = {"consensus_h0": 0.0, "consensus_h05": 0.05}
_CONSENSUS_MIN_SITES = 2


def _comb(n: int, k: int) -> int:
    if k < 0 or n < 0 or k > n:
        return 0
    return math.comb(n, k)


def bao_cover_rate(zodiacs: list[str], year: int) -> float:
    """k 个生肖至少有一个出现在 7 个号码里的概率。"""
    covered: set[int] = set()
    for zodiac in zodiacs:
        covered.update(zodiac_numbers(zodiac, year))
    outside = 49 - len(covered)
    total = _comb(49, 7)
    if total <= 0:
        return 0.0
    return 1.0 - _comb(outside, 7) / total


def all_present_rate(zodiacs: list[str], year: int) -> float:
    """这几个生肖全部出现在 7 个号码里的概率（容斥）。"""
    total = _comb(49, 7)
    if total <= 0:
        return 0.0
    acc = 0.0
    for r in range(len(zodiacs) + 1):
        for sub in combinations(zodiacs, r):
            covered: set[int] = set()
            for zodiac in sub:
                covered.update(zodiac_numbers(zodiac, year))
            acc += (-1) ** r * _comb(49 - len(covered), 7) / total
    return acc


def _pick_coldest(omit: dict[str, int]) -> str:
    return max(ZODIAC_ORDER, key=lambda z: (omit[z], -ZODIAC_ORDER.index(z)))


def _pick_gap(omit: dict[str, int], center: int) -> str:
    return max(
        ZODIAC_ORDER,
        key=lambda z: (-abs(omit[z] - center), -ZODIAC_ORDER.index(z)),
    )


def _pick_hot(hot: dict[str, int]) -> str:
    return max(ZODIAC_ORDER, key=lambda z: (hot[z], -ZODIAC_ORDER.index(z)))


def _current_winner(
    *,
    play: str,
    omit: dict[str, int],
    hot: dict[str, int],
    tip_raw: dict[str, float],
) -> str:
    return _current_ranked(play=play, omit=omit, hot=hot, tip_raw=tip_raw)[0]


def _current_ranked(
    *,
    play: str,
    omit: dict[str, int],
    hot: dict[str, int],
    tip_raw: dict[str, float],
) -> list[str]:
    if play == "bao_xiao":
        center = settings.bao_omit_center
        half = settings.bao_omit_half
        hot_full = settings.hot_window
        tip_weight = settings.weight_tip
    else:
        center = settings.tema_omit_center
        half = settings.tema_omit_half
        hot_full = settings.tema_hot_full
        tip_weight = 0.0
    omit_n = _gap_component(omit, center=center, half_width=half)
    hot_n = _scaled_component(hot, min_lead=settings.score_min_lead, full_at=hot_full)
    tip_n = _normalize(tip_raw) if tip_weight > 0 else {z: 0.0 for z in ZODIAC_ORDER}
    totals = {
        z: (
            settings.weight_omit * omit_n[z]
            + settings.weight_hot * hot_n[z]
            + tip_weight * tip_n[z]
        )
        for z in ZODIAC_ORDER
    }
    return sorted(
        ZODIAC_ORDER,
        key=lambda z: (totals[z], -abs(omit[z] - center), -ZODIAC_ORDER.index(z)),
        reverse=True,
    )


def _consensus_sites(bao_tips: list[dict[str, Any]], enabled: set[str]) -> dict[str, int]:
    """每个肖被几个启用站的包肖名单提到（同站只算一次）。"""
    sites: dict[str, set[str]] = {z: set() for z in ZODIAC_ORDER}
    for tip in bao_tips:
        site = str(tip.get("site_code") or "")
        if site not in enabled:
            continue
        for zodiac in tip.get("zodiacs") or []:
            if zodiac in sites:
                sites[zodiac].add(site)
    return {z: len(s) for z, s in sites.items()}


def _consensus_ranked(
    *,
    omit: dict[str, int],
    hot: dict[str, int],
    site_counts: dict[str, int],
    hot_weight: float,
) -> list[str]:
    """遗漏照旧；热度按 hot_weight；资料分只给至少两站同推的肖，按同推站数归一。"""
    center = settings.bao_omit_center
    omit_n = _gap_component(omit, center=center, half_width=settings.bao_omit_half)
    hot_n = _scaled_component(hot, min_lead=settings.score_min_lead, full_at=settings.hot_window)
    agreed = {
        z: float(c) if c >= _CONSENSUS_MIN_SITES else 0.0 for z, c in site_counts.items()
    }
    tip_n = _normalize(agreed)
    totals = {
        z: settings.weight_omit * omit_n[z] + hot_weight * hot_n[z] + settings.weight_tip * tip_n[z]
        for z in ZODIAC_ORDER
    }
    return sorted(
        ZODIAC_ORDER,
        key=lambda z: (totals[z], -abs(omit[z] - center), -ZODIAC_ORDER.index(z)),
        reverse=True,
    )


def _lock_year(ranked: list[str], anchor: str, size: int) -> list[str]:
    """当年肖（5 个号）固定在组里，其余名额按现行排名往下取。"""
    others = [zodiac for zodiac in ranked if zodiac != anchor]
    return [anchor, *others[: size - 1]]


def _all_hit(group: list[str], row: dict[str, Any]) -> int:
    return int(all(bao_xiao_hit(zodiac, row) for zodiac in group))


def _year_prior_note(by_year: list[dict[str, Any]], override: dict[str, dict[str, int]]) -> str:
    """线上已经改用当年肖。by_year 仍由调用方传入，句子里不再用它否决。"""
    del by_year
    parts = [
        "号码先验按生肖占几个号计算（当年肖 5 个，其余各 4 个），不是 12 肖均匀。",
        "线上单肖固定为当年肖；三连、五连把当年肖放在第一位，其余按旧公式排名。这张表里的旧公式只作对照。",
    ]
    single = override["single"]
    parts.append(
        f"单肖旧公式改选非当年肖 {single['changed']} 期，"
        f"这些期旧公式中 {single['current_hits']}、当年肖中 {single['year_hits']}。"
    )
    for key, label in (("lian3", "三连肖"), ("lian5", "五连肖")):
        item = override[key]
        parts.append(
            f"{label}组不同的 {item['changed']} 期，"
            f"旧公式全中 {item['current_hits']}、锁当年肖全中 {item['year_hits']}。"
        )
    parts.append("分年的格子只用来看旧公式有没有高出当年肖，不拿去改回旧公式。")
    return "".join(parts)


def _known_before_draw(tip: dict[str, Any], draw: dict[str, Any]) -> bool:
    """只有第一次抓到的时间早于该期开奖 21:32，才算预测时已经看得到。"""
    draw_day = draw.get("draw_date")
    if isinstance(draw_day, datetime):
        draw_day = draw_day.date()
    if not isinstance(draw_day, date):
        return False
    seen = tip.get("first_seen_at") or tip.get("scraped_at")
    if not isinstance(seen, datetime):
        return False
    return seen < datetime.combine(draw_day, _DRAW_CLOCK)


def run_walkforward() -> dict[str, Any] | None:
    draws = list_draws_asc()
    if len(draws) <= _START:
        return None

    stats = {
        name: {"tema": 0, "bao": 0, "bao_expected": 0.0, "n": 0}
        for name in ("cold", "gap", "hot", "current", "year", *_CONSENSUS_HOT_WEIGHTS)
    }
    enabled = {site.code for site in enabled_tip_sites()}
    consensus = {
        "periods_with_tips": 0,
        "periods_agreed": 0,
        "variants": {
            key: {"changed": 0, "changed_hits": 0, "changed_hits_without_tip": 0}
            for key in _CONSENSUS_HOT_WEIGHTS
        },
    }
    this_year = lunar_year_for(None)
    single_bao = sum(bao_cover_rate([z], this_year) for z in ZODIAC_ORDER) / len(ZODIAC_ORDER)
    tips_by_period = list_tips_by_period()

    tema_tip_hit = 0
    tema_tip_base = 0.0
    tema_tip_n = 0
    by_count: dict[int, list[int]] = {}
    bao_used = 0
    bao_skipped = 0
    tema_skipped = 0
    lian = {
        kind: {size: {"hits": 0, "expected": 0.0} for size in (3, 5)}
        for kind in ("current", "year")
    }
    by_year: dict[int, dict[str, Any]] = {}
    override = {
        key: {"changed": 0, "current_hits": 0, "year_hits": 0}
        for key in ("single", "lian3", "lian5")
    }

    for i in range(_START, len(draws)):
        history = draws[:i]
        row = draws[i]
        period = int(row["period"])
        special = row["special_zodiac"]
        omit_t = _omit_tema(history)
        omit_b = _omit_bao(history)
        hot_t = _hot_tema(history, settings.hot_window)
        hot_b = _hot_bao(history, settings.hot_window)
        stored = tips_by_period.get(period, [])
        tips = [tip for tip in stored if _known_before_draw(tip, row)]
        bao_used += len(contributing_tips(tips, "bao_xiao"))
        bao_skipped += len(contributing_tips(stored, "bao_xiao")) - len(contributing_tips(tips, "bao_xiao"))
        tema_skipped += len(contributing_tips(stored, "te_ma")) - len(contributing_tips(tips, "te_ma"))
        bao_tips = contributing_tips(tips, "bao_xiao")
        if bao_tips:
            weights = site_weights_for_period("bao_xiao", period)
            tip_raw = tip_scores_for_period(
                period, tips, play_type="bao_xiao", site_weights=weights
            )
        else:
            tip_raw = {z: 0.0 for z in ZODIAC_ORDER}

        bao_ranked = _current_ranked(play="bao_xiao", omit=omit_b, hot=hot_b, tip_raw=tip_raw)
        picks = {
            "cold": (_pick_coldest(omit_t), _pick_coldest(omit_b)),
            "gap": (
                _pick_gap(omit_t, settings.tema_omit_center),
                _pick_gap(omit_b, settings.bao_omit_center),
            ),
            "hot": (_pick_hot(hot_t), _pick_hot(hot_b)),
            "current": (
                _current_winner(play="te_ma", omit=omit_t, hot=hot_t, tip_raw=tip_raw),
                bao_ranked[0],
            ),
        }
        site_counts = _consensus_sites(bao_tips, enabled)
        no_sites = {z: 0 for z in ZODIAC_ORDER}
        if any(site_counts.values()):
            consensus["periods_with_tips"] += 1
        if max(site_counts.values()) >= _CONSENSUS_MIN_SITES:
            consensus["periods_agreed"] += 1
        for key, hot_weight in _CONSENSUS_HOT_WEIGHTS.items():
            pick = _consensus_ranked(
                omit=omit_b, hot=hot_b, site_counts=site_counts, hot_weight=hot_weight
            )[0]
            plain = _consensus_ranked(
                omit=omit_b, hot=hot_b, site_counts=no_sites, hot_weight=hot_weight
            )[0]
            picks[key] = (None, pick)
            if pick != plain:
                variant = consensus["variants"][key]
                variant["changed"] += 1
                variant["changed_hits"] += int(bao_xiao_hit(pick, row))
                variant["changed_hits_without_tip"] += int(bao_xiao_hit(plain, row))

        draw_year = lunar_year_for(row.get("draw_date"))
        anchor = year_zodiac(draw_year)
        picks["year"] = (None, anchor)
        if bao_ranked[0] != anchor:
            override["single"]["changed"] += 1
            override["single"]["current_hits"] += int(bao_xiao_hit(bao_ranked[0], row))
            override["single"]["year_hits"] += int(bao_xiao_hit(anchor, row))
        groups = {
            3: (bao_ranked[:3], _lock_year(bao_ranked, anchor, 3)),
            5: (bao_ranked[:5], _lock_year(bao_ranked, anchor, 5)),
        }
        year_row = by_year.get(draw_year)
        if year_row is None:
            year_row = {
                "year": draw_year,
                "zodiac": anchor,
                "n": 0,
                "current_bao": 0,
                "year_bao": 0,
                "current_lian3": 0,
                "year_lian3": 0,
                "current_lian5": 0,
                "year_lian5": 0,
            }
            by_year[draw_year] = year_row
        year_row["n"] += 1
        year_row["current_bao"] += int(bao_xiao_hit(bao_ranked[0], row))
        year_row["year_bao"] += int(bao_xiao_hit(anchor, row))
        for size, (current_group, year_group) in groups.items():
            play = f"lian{size}"
            current_hit = _all_hit(current_group, row)
            year_hit = _all_hit(year_group, row)
            lian["current"][size]["hits"] += current_hit
            lian["year"][size]["hits"] += year_hit
            lian["current"][size]["expected"] += all_present_rate(current_group, draw_year)
            lian["year"][size]["expected"] += all_present_rate(year_group, draw_year)
            year_row[f"current_{play}"] += current_hit
            year_row[f"year_{play}"] += year_hit
            if set(current_group) != set(year_group):
                override[play]["changed"] += 1
                override[play]["current_hits"] += current_hit
                override[play]["year_hits"] += year_hit
        for name, (tema_z, bao_z) in picks.items():
            stats[name]["n"] += 1
            stats[name]["bao_expected"] += bao_cover_rate([bao_z], draw_year)
            if tema_z is not None:
                stats[name]["tema"] += int(tema_z == special)
            stats[name]["bao"] += int(bao_xiao_hit(bao_z, row))

        for tip in contributing_tips(tips, "te_ma"):
            zodiacs = list(tip.get("zodiacs") or [])
            if not zodiacs:
                continue
            count = len(zodiacs)
            hit = int(special in zodiacs)
            tema_tip_hit += hit
            tema_tip_base += count / 12
            tema_tip_n += 1
            bucket = by_count.setdefault(count, [0, 0])
            bucket[0] += hit
            bucket[1] += 1

    n = stats["cold"]["n"]
    labels = (
        ("cold", "追最冷"),
        ("gap", "靠近典型间隔"),
        ("hot", "只看热度"),
        ("current", "旧公式"),
        ("year", "永远当年肖"),
        ("consensus_h0", "共识（热度 0）"),
        ("consensus_h05", "共识（热度 0.05）"),
    )
    tema_keys = {"cold", "gap", "hot", "current"}
    if tema_tip_n and tema_tip_hit <= tema_tip_base * 1.15:
        tip_note = "特码资料没有明显高于名单长度 / 12，权重保持 0。"
        keep_zero = True
    elif tema_tip_n:
        tip_note = "特码资料覆盖高于名单基准，仍不自动加进排名。"
        keep_zero = False
    else:
        tip_note = "这些期里没有开奖前就能看到的特码名单。"
        keep_zero = True
    tip_note += (
        f" 包肖资料只采用第一次抓到时间早于开奖 21:32 的名单：用了 {bao_used} 条，"
        f"来不及证明的 {bao_skipped} 条没有进入旧公式。"
    )
    if tema_skipped:
        tip_note += f" 特码对照同样去掉来不及证明的 {tema_skipped} 条。"

    return {
        "rule": _RULE,
        "from_period": int(draws[_START]["period"]),
        "through_period": int(draws[-1]["period"]),
        "n": n,
        "tema_baseline": 0.083,
        "bao_baseline": round(single_bao, 4),
        "rows": [
            {
                "key": key,
                "label": label,
                "tema_hits": stats[key]["tema"] if key in tema_keys else None,
                "bao_hits": stats[key]["bao"],
                "bao_expected": round(stats[key]["bao_expected"], 1),
                "n": stats[key]["n"],
            }
            for key, label in labels
        ],
        "consensus": {
            "min_sites": _CONSENSUS_MIN_SITES,
            "periods_with_tips": consensus["periods_with_tips"],
            "periods_agreed": consensus["periods_agreed"],
            "variants": [
                {"key": key, "hot_weight": weight, **consensus["variants"][key]}
                for key, weight in _CONSENSUS_HOT_WEIGHTS.items()
            ],
        },
        "lian": [
            {
                "key": f"lian{size}" if kind == "current" else f"lian{size}_year",
                "label": (
                    f"{'三连肖' if size == 3 else '五连肖'}·"
                    f"{'旧公式' if kind == 'current' else '锁当年肖'}"
                ),
                "hits": lian[kind][size]["hits"],
                "expected": round(lian[kind][size]["expected"], 1),
                "n": n,
            }
            for size in (3, 5)
            for kind in ("current", "year")
        ],
        "year_prior": {
            "by_year": [by_year[year] for year in sorted(by_year)],
            "override": override,
            "note": _year_prior_note([by_year[year] for year in sorted(by_year)], override),
        },
        "tema_tips": {
            "records": tema_tip_n,
            "hits": tema_tip_hit,
            "expected_hits": round(tema_tip_base, 1),
            "keep_weight_zero": keep_zero,
            "by_count": [
                {"count": count, "hits": pair[0], "n": pair[1]}
                for count, pair in sorted(by_count.items())
            ],
            "note": tip_note,
        },
    }


def refresh_backtest_if_needed(latest_drawn_period: int) -> dict[str, Any]:
    """新开奖期还没对照过时才重算。同一期重复刷新直接沿用上次结果。"""
    current = latest_backtest_snapshot()
    same_period = current and int(current.get("through_period") or 0) >= latest_drawn_period
    same_rule = bool(current) and current.get("rule") == _RULE
    complete = (
        bool(current)
        and "lian" in current
        and "consensus" in current
        and "year_prior" in current
    )
    if same_period and same_rule and complete:
        return {"updated": False, "snapshot": current}
    snapshot = run_walkforward()
    if not snapshot:
        return {"updated": False, "snapshot": current}
    save_backtest_snapshot(int(snapshot["through_period"]), snapshot)
    saved = latest_backtest_snapshot()
    return {"updated": True, "snapshot": saved or snapshot}
