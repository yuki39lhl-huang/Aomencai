from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.db import ping_db
from app.jobs.pipeline import refresh_all
from app.repositories import latest_draw, latest_scrape_run, list_draws
from app.services.reconcile import hit_summary, reconcile_pending, site_weights_for_period
from app.services.scoring import latest_recommendation, score_for_period

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
        "scrape_run": run,
        "site_weights": weights,
        "hits": hit_summary(limit=12),
    }


@router.get("/hit-stats")
def hit_stats_api():
    draw = latest_draw()
    period = int(draw["period"]) + 1 if draw else 1
    return {
        "hits": hit_summary(limit=24),
        "site_weights": {
            "bao_xiao": site_weights_for_period("bao_xiao", period),
            "te_ma": site_weights_for_period("te_ma", period),
        },
    }


@router.post("/reconcile")
def reconcile_api():
    return reconcile_pending()


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
