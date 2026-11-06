"""命令行打印滚动回测。只写对照结果，不写 recommend_log。"""
from __future__ import annotations

from app.repositories import save_backtest_snapshot
from app.services.walkforward import run_walkforward


def _rate(hits: int | None, total: int) -> str:
    if hits is None or total <= 0:
        return "—"
    return f"{hits}/{total}={hits / total:.1%}"


def _pct_points(delta: int | None, total: int) -> str:
    if delta is None or total <= 0:
        return "—"
    return f"{delta:+d}（{delta / total * 100:+.1f}pt）"


def main() -> None:
    snapshot = run_walkforward()
    if not snapshot:
        print("开奖期数不够")
        return
    save_backtest_snapshot(int(snapshot["through_period"]), snapshot)
    bao_base = float(snapshot["bao_baseline"])
    n = int(snapshot["n"])
    print(
        f"滚动回测 {snapshot['from_period']}–{snapshot['through_period']}，"
        f"共 {n} 期。预测时只用更早开奖。规则 {snapshot['rule']}"
    )
    print(f"随机一肖基准：特码 8.3%，包肖 {bao_base:.1%}")
    print()
    print("策略 | 用上 tip 期数 | 特码 | 包肖 | 相对现行包肖 | 相对现行特码")
    for row in snapshot["rows"]:
        tip_n = row.get("tip_periods", 0)
        print(
            f"{row['label']} | tip期 {tip_n} | 特码 {_rate(row['tema_hits'], n)}"
            f" | 包肖 {_rate(int(row['bao_hits']), n)}"
            f"（先验 {row.get('bao_expected', '—')}）"
            f" | 包肖差 {_pct_points(row.get('bao_delta_vs_current'), n)}"
            f" | 特码差 {_pct_points(row.get('tema_delta_vs_current'), n)}"
        )
    cons = snapshot.get("consensus") or {}
    if cons:
        print()
        print(
            f"共识：开奖前有启用站包肖名单 {cons.get('periods_with_tips')} 期；"
            f"至少 {cons.get('min_sites')} 站同推 {cons.get('periods_agreed')} 期；"
            f"无共识回退 {cons.get('periods_fallback')} 期"
        )
        for item in cons.get("variants") or []:
            print(
                f"  {item.get('label') or item['key']}："
                f"资料改动推荐 {item['changed']} 期，"
                f"这些期共识中 {item['changed_hits']}、无 tip 中 {item['changed_hits_without_tip']}"
            )
    for item in snapshot.get("lian") or []:
        print(
            f"{item['label']} | 全出 {_rate(int(item['hits']), int(item['n']))}"
            f"（号码先验 {item['expected']} 次）"
        )
    prior = snapshot.get("year_prior") or {}
    if prior.get("note"):
        print()
        print(prior["note"])
    tips = snapshot["tema_tips"]
    print()
    print(f"特码资料（一肖到三肖，有名单的记录 {tips['records']} 条）")
    if tips["records"]:
        records = int(tips["records"])
        hits = int(tips["hits"])
        print(
            f"覆盖 {hits}/{records}={hits / records:.1%}，"
            f"按名单长度/12 的期望 {tips['expected_hits']} 次"
        )
    print(tips["note"])
    kill = snapshot.get("tema_kill") or {}
    if kill:
        kn = int(kill.get("periods_with_kill") or 0)
        print()
        print(f"特码绝杀对照（有明文绝杀 {kn} 期）")
        if kn:
            print(
                f"  现行遗漏+热度 {_rate(kill.get('current_hits'), kn)} | "
                f"绝杀直荐 {_rate(kill.get('kill_as_pick_hits'), kn)} | "
                f"回避绝杀 {_rate(kill.get('kill_avoid_hits'), kn)} | "
                f"极低权加分({kill.get('boost_weight')}) {_rate(kill.get('kill_boost_hits'), kn)}"
            )
        print(kill.get("note") or "")
    print()
    print(f"已写入 backtest_snapshot through_period={snapshot['through_period']}")


if __name__ == "__main__":
    main()
