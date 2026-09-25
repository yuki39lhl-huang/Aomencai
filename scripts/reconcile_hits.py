"""手动对账：系统推荐 + 站点 tip 命中。"""
from app.services.reconcile import hit_summary, reconcile_pending, site_weights_for_period
from app.repositories import latest_draw


def main() -> None:
    result = reconcile_pending()
    print("=== 对账完成 ===")
    print("recommend periods:", result["recommend_periods"])
    print("site periods:", result["site_periods"])
    for row in result["recommend"]:
        flag = "中" if row["hit"] else "否"
        print(f"  {row['period']} {row['play_type']} 荐{row['zodiac']} -> {flag}")

    draw = latest_draw()
    period = int(draw["period"]) + 1 if draw else 1
    print("=== 命中汇总 ===")
    print(hit_summary(limit=12))
    print("=== 站点权重(包肖) ===")
    print(site_weights_for_period("bao_xiao", period))
    print("=== 站点权重(特码) ===")
    print(site_weights_for_period("te_ma", period))


if __name__ == "__main__":
    main()
