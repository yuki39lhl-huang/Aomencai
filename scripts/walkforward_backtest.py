"""命令行打印滚动回测。平时不用跑：新开奖写入后，刷新分析会自动更新页面上的对照。"""
from __future__ import annotations

from app.services.walkforward import run_walkforward


def _rate(hits: int | None, total: int) -> str:
    if hits is None or total <= 0:
        return "—"
    return f"{hits}/{total}={hits / total:.1%}"


def main() -> None:
    snapshot = run_walkforward()
    if not snapshot:
        print("开奖期数不够")
        return
    bao_base = float(snapshot["bao_baseline"])
    print(
        f"滚动回测 {snapshot['from_period']}–{snapshot['through_period']}，"
        f"共 {snapshot['n']} 期。预测时只用更早开奖。"
    )
    print(f"随机一肖基准：特码 8.3%，包肖 {bao_base:.1%}")
    for row in snapshot["rows"]:
        n = int(row["n"])
        tema = row["tema_hits"]
        print(
            f"{row['label']} | 特码 {_rate(tema, n)}{'（基准 8.3%）' if tema is not None else ''}"
            f" | 包肖 {_rate(int(row['bao_hits']), n)}（随机基准 {bao_base:.1%}）"
            f" | 号码先验 {row.get('bao_expected', '—')} 次"
        )
    cons = snapshot.get("consensus")
    if cons:
        print()
        print(
            f"共识资料：开奖前有启用站包肖名单的 {cons['periods_with_tips']} 期，"
            f"其中至少 {cons['min_sites']} 站同推某肖的 {cons['periods_agreed']} 期"
        )
        for item in cons["variants"]:
            print(
                f"  热度 {item['hot_weight']}：资料改动了推荐的 {item['changed']} 期，"
                f"这些期共识中 {item['changed_hits']} 次，不加资料中 {item['changed_hits_without_tip']} 次"
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
    for item in prior.get("by_year") or []:
        print(
            f"  {item['year']}{item['zodiac']} {item['n']} 期 | "
            f"单肖现行 {item['current_bao']} / 永远当年肖 {item['year_bao']} | "
            f"三连现行 {item['current_lian3']} / 锁当年 {item['year_lian3']} | "
            f"五连现行 {item['current_lian5']} / 锁当年 {item['year_lian5']}"
        )
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
        for item in tips["by_count"]:
            count = int(item["count"])
            hit = int(item["hits"])
            total = int(item["n"])
            print(f"  {count}肖 {hit}/{total}={hit / total:.1%}，基准 {count / 12:.1%}")
    print(tips["note"])


if __name__ == "__main__":
    main()
