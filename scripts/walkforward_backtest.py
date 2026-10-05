"""滚动回测：预测第 N 期时只用更早的开奖。不写推荐，不改已有中没中。"""
from __future__ import annotations

import math

from app.config import settings
from app.repositories import list_draws_asc, list_tips
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
from app.services.zodiac import ZODIAC_ORDER, bao_xiao_hit, zodiac_numbers


def _comb(n: int, k: int) -> int:
    if k < 0 or n < 0 or k > n:
        return 0
    return math.comb(n, k)


def bao_cover_rate(zodiacs: list[str]) -> float:
    """k 个生肖至少有一个出现在 7 个号码里的概率。"""
    covered: set[int] = set()
    for zodiac in zodiacs:
        covered.update(zodiac_numbers(zodiac, settings.lunar_year))
    outside = 49 - len(covered)
    total = _comb(49, 7)
    if total <= 0:
        return 0.0
    return 1.0 - _comb(outside, 7) / total


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
    return max(
        ZODIAC_ORDER,
        key=lambda z: (totals[z], -abs(omit[z] - center), -ZODIAC_ORDER.index(z)),
    )


def _rate(hits: int, total: int) -> str:
    if total <= 0:
        return "—"
    return f"{hits}/{total}={hits / total:.1%}"


def main() -> None:
    draws = list_draws_asc()
    start = 40
    if len(draws) <= start:
        print("开奖期数不够")
        return

    stats = {
        name: {"tema": 0, "bao": 0, "n": 0}
        for name in ("cold", "gap", "hot", "current")
    }
    single_bao = sum(bao_cover_rate([z]) for z in ZODIAC_ORDER) / len(ZODIAC_ORDER)

    tema_tip_hit = 0
    tema_tip_base = 0.0
    tema_tip_n = 0
    by_count: dict[int, list[int]] = {}

    for i in range(start, len(draws)):
        history = draws[:i]
        row = draws[i]
        period = int(row["period"])
        special = row["special_zodiac"]
        omit_t = _omit_tema(history)
        omit_b = _omit_bao(history)
        hot_t = _hot_tema(history, settings.hot_window)
        hot_b = _hot_bao(history, settings.hot_window)
        tips = list_tips(period)
        bao_tips = contributing_tips(tips, "bao_xiao")
        if bao_tips:
            weights = site_weights_for_period("bao_xiao", period)
            tip_raw = tip_scores_for_period(
                period, tips, play_type="bao_xiao", site_weights=weights
            )
        else:
            tip_raw = {z: 0.0 for z in ZODIAC_ORDER}

        picks = {
            "cold": (_pick_coldest(omit_t), _pick_coldest(omit_b)),
            "gap": (
                _pick_gap(omit_t, settings.tema_omit_center),
                _pick_gap(omit_b, settings.bao_omit_center),
            ),
            "hot": (_pick_hot(hot_t), _pick_hot(hot_b)),
            "current": (
                _current_winner(play="te_ma", omit=omit_t, hot=hot_t, tip_raw=tip_raw),
                _current_winner(play="bao_xiao", omit=omit_b, hot=hot_b, tip_raw=tip_raw),
            ),
        }
        for name, (tema_z, bao_z) in picks.items():
            stats[name]["n"] += 1
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
    print(f"滚动回测 {draws[start]['period']}–{draws[-1]['period']}，共 {n} 期。预测时只用更早开奖。")
    print(f"随机一肖基准：特码 8.3%，包肖 {single_bao:.1%}")
    rows = [
        ("追最冷", "cold"),
        ("靠近典型间隔（现行遗漏）", "gap"),
        ("只看热度", "hot"),
        ("现行公式", "current"),
    ]
    for label, key in rows:
        item = stats[key]
        print(
            f"{label} | 特码 {_rate(item['tema'], item['n'])}（基准 8.3%）"
            f" | 包肖 {_rate(item['bao'], item['n'])}（基准 {single_bao:.1%}）"
        )

    print()
    print(f"特码资料（一肖到三肖，有名单的记录 {tema_tip_n} 条）")
    if tema_tip_n:
        print(
            f"覆盖 {tema_tip_hit}/{tema_tip_n}={tema_tip_hit / tema_tip_n:.1%}，"
            f"按名单长度/12 的期望 {tema_tip_base:.1f} 次（{tema_tip_base / tema_tip_n:.1%}）"
        )
        for count in sorted(by_count):
            hit, total = by_count[count]
            print(f"  {count}肖 {hit}/{total}={hit / total:.1%}，基准 {count / 12:.1%}")
        if tema_tip_hit <= tema_tip_base * 1.15:
            print("没有明显高于名单长度对应的基准，特码资料权重保持 0。")
        else:
            print("覆盖次数高于名单基准，仍不自动加进排名，先继续积累期数。")
    else:
        print("这些期里没有特码名单。")


if __name__ == "__main__":
    main()
