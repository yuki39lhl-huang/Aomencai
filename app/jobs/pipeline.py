from __future__ import annotations

from typing import Any

from app.repositories import finish_scrape_run, latest_draw, start_scrape_run
from app.scrapers.history import sync_history, sync_live_data
from app.scrapers.tips import sync_tips
from app.services.reconcile import (
    reconcile_pending,
    reconcile_recommend_period,
    reconcile_site_tips_period,
)
from app.services.scoring import score_for_period


async def refresh_all(*, full_history: bool = False) -> dict[str, Any]:
    run_id = start_scrape_run("bootstrap" if full_history else "refresh")
    summary: dict[str, Any] = {"full_history": full_history}
    try:
        if full_history:
            summary["history"] = await sync_history()
        live = await sync_live_data()
        summary["live"] = live

        if not full_history:
            try:
                summary["history_light"] = await sync_history()
            except Exception as exc:
                summary["history_light_error"] = f"{type(exc).__name__}: {exc}"

        draw = latest_draw()
        if not draw:
            raise RuntimeError("未获取到开奖数据")

        # 开奖入库后先对账已开期，再抓下期 tip / 打分（降权用历史命中）
        summary["reconcile"] = reconcile_pending()
        latest_period = int(draw["period"])
        summary["reconcile_latest"] = {
            "recommend": reconcile_recommend_period(latest_period),
            "site_tips": reconcile_site_tips_period(latest_period),
        }

        # 默认预测「最新已开奖期 + 1」；live 未开奖时 waiting_period 就是当期
        target_period = latest_period + 1
        if live:
            if live.get("drawn") and live.get("next_period"):
                target_period = int(live["next_period"])
            elif live.get("waiting_period"):
                target_period = int(live["waiting_period"])

        summary["tips"] = await sync_tips(target_period)
        summary["recommend"] = score_for_period(target_period)
        bao = summary["recommend"]["bao_xiao"]["zodiac"]
        tema = summary["recommend"]["te_ma"]["zodiac"]
        finish_scrape_run(
            run_id,
            "success",
            f"完成，{target_period}期 包肖={bao} 特码={tema}",
        )
        summary["ok"] = True
        return summary
    except Exception as exc:
        finish_scrape_run(run_id, "failed", str(exc))
        summary["ok"] = False
        summary["error"] = str(exc)
        raise
