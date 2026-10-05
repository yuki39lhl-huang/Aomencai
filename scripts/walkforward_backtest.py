"""命令行打印滚动回测。平时不用跑：新开奖写入后，刷新分析会自动更新页面上的对照。"""
from __future__ import annotations

from app.services.walkforward import run_walkforward


def _rate(hits: int, total: int) -> str:
    if total <= 0:
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
        print(
            f"{row['label']} | 特码 {_rate(int(row['tema_hits']), n)}（基准 8.3%）"
            f" | 包肖 {_rate(int(row['bao_hits']), n)}（基准 {bao_base:.1%}）"
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
