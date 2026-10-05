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
from app.services.walkforward import refresh_backtest_if_needed


def _exc_text(exc: BaseException) -> str:
    detail = str(exc).strip()
    if detail:
        return f"{type(exc).__name__}: {detail}"
    return f"{type(exc).__name__}: {exc!r}"


async def _sync_live_safe(summary: dict[str, Any]) -> None:
    """data.txt 被拦成网页或断线时，不中断后续历史页和打分。"""
    try:
        summary["live"] = await sync_live_data()
    except Exception as exc:
        summary["live"] = None
        summary["live_error"] = _exc_text(exc)


async def _sync_history_safe(summary: dict[str, Any], key: str) -> None:
    """历史页经常断连；失败只记下来，不中断实时开奖和后续打分。"""
    try:
        summary[key] = await sync_history()
    except Exception as exc:
        summary[f"{key}_error"] = _exc_text(exc)


async def refresh_all(*, full_history: bool = False) -> dict[str, Any]:
    run_id = start_scrape_run("bootstrap" if full_history else "refresh")
    summary: dict[str, Any] = {"full_history": full_history}
    try:
        await _sync_live_safe(summary)
        await _sync_history_safe(summary, "history" if full_history else "history_light")
        live = summary.get("live")

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
        try:
            summary["backtest"] = refresh_backtest_if_needed(latest_period)
        except Exception as exc:
            summary["backtest_error"] = _exc_text(exc)

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
        detail = _exc_text(exc)
        finish_scrape_run(run_id, "failed", detail)
        summary["ok"] = False
        summary["error"] = detail
        raise
