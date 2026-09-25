import asyncio

from app.config import settings
from app.db import db_cursor
from app.scrapers.history import sync_history, sync_live_data
from app.services.zodiac import bao_xiao_hit


async def refresh_draws() -> None:
    live = await sync_live_data()
    print("live:", live)
    try:
        print("history:", await sync_history())
    except Exception as exc:
        print("history err:", type(exc).__name__, exc)


asyncio.run(refresh_draws())

with db_cursor() as cur:
    cur.execute(
        "SELECT period, draw_date, n1,n2,n3,n4,n5,n6, special, special_zodiac "
        "FROM draw_result WHERE period>=265 ORDER BY period"
    )
    draws = cur.fetchall()
    cur.execute(
        "SELECT period, play_type, zodiac FROM recommend_log "
        "WHERE period>=265 ORDER BY period, play_type"
    )
    recs = cur.fetchall()

by: dict = {}
for r in recs:
    by.setdefault(r["period"], {})[r["play_type"]] = r["zodiac"]

print("=== 对账 ===")
for d in draws:
    p = d["period"]
    bao = by.get(p, {}).get("bao_xiao")
    tema = by.get(p, {}).get("te_ma")
    if not bao and not tema:
        print(p, "无推荐", "特开", d["special_zodiac"], d["special"])
        continue
    bh = bao_xiao_hit(bao, d, settings.lunar_year) if bao else False
    th = tema == d["special_zodiac"] if tema else False
    nums = [d["n1"], d["n2"], d["n3"], d["n4"], d["n5"], d["n6"], d["special"]]
    print(
        f"{p}期 开奖平+特={nums} 特码={d['special']}/{d['special_zodiac']} | "
        f"包肖荐{bao}={'中' if bh else '否'} | "
        f"特码荐{tema}={'中' if th else '否'}"
    )
