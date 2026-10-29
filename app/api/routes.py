from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import ping_db
from app.jobs.pipeline import refresh_all
from app.repositories import (
    expire_stale_scrape_runs,
    get_draw,
    get_recommends_for_period,
    latest_draw,
    latest_backtest_snapshot,
    latest_scrape_run,
    list_draws,
    list_draws_asc,
    list_site_alerts,
    update_recommend_hit,
)
from app.services.reconcile import hit_summary, reconcile_pending, site_weights_for_period
from app.scrapers.tips import FAIL_REASON_LABEL
from app.services.scoring import latest_recommendation, score_for_period, year_zodiac_for_period

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    try:
        ok = ping_db()
    except Exception as exc:
        return JSONResponse({"ok": False, "db": False, "error": str(exc)}, status_code=500)
    return {"ok": True, "db": ok}


@router.get("/draws")
def draws(limit: int = 30):
    return {"items": list_draws(limit=limit)}


@router.get("/latest-recommend")
def latest_recommend_api():
    rec = latest_recommendation()
    draw = latest_draw()
    run = latest_scrape_run()
    period = (rec or {}).get("period") or (int(draw["period"]) + 1 if draw else None)
    weights = None
    if period:
        weights = {
            "bao_xiao": site_weights_for_period("bao_xiao", int(period)),
            "te_ma": site_weights_for_period("te_ma", int(period)),
        }
    return {
        "recommend": rec,
        "latest_draw": draw,
        "settle": _settle_target(rec),
        "scrape_run": run,
        "site_weights": weights,
        "hits": hit_summary(limit=20),
        "backtest": latest_backtest_snapshot(),
        "year_zodiac": _panel_year_zodiac(rec, period),
        "site_alerts": [
            {
                "site": row["site_code"],
                "fail_streak": int(row["fail_streak"]),
                "fail_reason": row.get("last_reason"),
                "fail_label": FAIL_REASON_LABEL.get(
                    row.get("last_reason") or "", row.get("last_reason")
                ),
                "last_period": row.get("last_period"),
                "reuse": (
                    "same_period"
                    if period is not None
                    and row.get("last_period") is not None
                    and int(row["last_period"]) == int(period)
                    else "prior_period"
                ),
            }
            for row in list_site_alerts()
        ],
    }


def _panel_year_zodiac(rec: dict | None, period: int | None) -> str | None:
    """面板年肖跟当期推荐详情或 year_zodiac_for_period，不用今天硬算。"""
    if rec:
        bao = rec.get("bao_xiao") or {}
        detail = bao.get("score_detail") or {}
        if isinstance(detail, dict) and detail.get("year_zodiac"):
            return str(detail["year_zodiac"])
    if period is None:
        return None
    return year_zodiac_for_period(int(period), list_draws_asc())


class ManualHitBody(BaseModel):
    period: int
    bao_xiao: bool
    te_ma: bool


def _hit_flag(value: object) -> bool | None:
    if value is None:
        return None
    return bool(int(value))  # type: ignore[arg-type]


def _brief_pick(row: dict | None) -> dict | None:
    if not row:
        return None
    return {"zodiac": row.get("zodiac"), "hit": _hit_flag(row.get("hit"))}


def _settle_target(rec: dict | None) -> dict | None:
    """录入区跟当前预测同一期、同一生肖，避免还停在上一期。"""
    if not rec:
        return None
    period = int(rec["period"])
    bao = rec.get("bao_xiao")
    tema = rec.get("te_ma")
    if not bao and not tema:
        return None
    return {
        "period": period,
        "drawn": get_draw(period) is not None,
        "bao_xiao": _brief_pick(bao),
        "te_ma": _brief_pick(tema),
    }


@router.post("/manual-hit")
def manual_hit(body: ManualHitBody):
    rows = get_recommends_for_period(body.period)
    by_type = {r["play_type"]: r for r in rows}
    missing = [name for name in ("bao_xiao", "te_ma") if name not in by_type]
    if missing:
        raise HTTPException(status_code=400, detail=f"{body.period}期还没有完整推荐，无法录入")
    update_recommend_hit(body.period, "bao_xiao", body.bao_xiao)
    update_recommend_hit(body.period, "te_ma", body.te_ma)
    return {
        "ok": True,
        "period": body.period,
        "bao_xiao": body.bao_xiao,
        "te_ma": body.te_ma,
    }


@router.post("/reconcile")
def reconcile_api():
    return reconcile_pending()


@router.post("/cleanup-scrape-runs")
def cleanup_scrape_runs(max_minutes: int = 30):
    """把卡住的 running 任务标成失败。刷新开始时也会自动做一次。"""
    cleared = expire_stale_scrape_runs(max_minutes=max_minutes)
    return {"ok": True, "expired": cleared, "max_minutes": max_minutes}


@router.post("/refresh")
async def refresh(full_history: bool = True):
    try:
        result = await refresh_all(full_history=full_history)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


@router.post("/rescore")
def rescore(period: int | None = None):
    draw = latest_draw()
    if not draw:
        raise HTTPException(status_code=400, detail="没有开奖数据")
    target = period or int(draw["period"]) + 1
    try:
        return score_for_period(target)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
