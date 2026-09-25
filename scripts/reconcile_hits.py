from app.config import settings
from app.db import db_cursor
from app.services.zodiac import bao_xiao_hit

with db_cursor() as cur:
    cur.execute(
        "SELECT period, play_type, zodiac, score, created_at "
        "FROM recommend_log ORDER BY period DESC, play_type LIMIT 40"
    )
    recs = cur.fetchall()
    cur.execute(
        "SELECT period, n1,n2,n3,n4,n5,n6, special, special_zodiac, draw_date "
        "FROM draw_result ORDER BY period DESC LIMIT 15"
    )
    draws = cur.fetchall()

draw_map = {d["period"]: d for d in draws}
print("=== 最近开奖 ===")
for d in draws[:10]:
    print(d["period"], d["draw_date"], "特", d["special"], d["special_zodiac"])

by: dict = {}
for r in recs:
    by.setdefault(r["period"], {})[r["play_type"]] = r

print("=== 推荐对账 ===")
for p in sorted(by.keys()):
    d = draw_map.get(p)
    bao = (by[p].get("bao_xiao") or {}).get("zodiac")
    tema = (by[p].get("te_ma") or {}).get("zodiac")
    if not d:
        print(f"{p} 未开奖 包肖={bao} 特码={tema}")
        continue
    bao_hit = bao_xiao_hit(bao, d, settings.lunar_year) if bao else False
    tema_hit = tema == d["special_zodiac"] if tema else False
    print(
        f"{p} 包肖荐{bao}->{'中' if bao_hit else '否'} | "
        f"特码荐{tema}/实开{d['special_zodiac']}->{'中' if tema_hit else '否'}"
    )
