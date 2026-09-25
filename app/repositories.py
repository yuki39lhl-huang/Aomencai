from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from app.db import db_cursor


def upsert_draw(
    *,
    period: int,
    draw_date: date | None,
    numbers: list[int],
    special: int,
    special_zodiac: str,
    source: str,
) -> None:
    if len(numbers) != 6:
        raise ValueError("平码必须是6个")
    sql = """
    INSERT INTO draw_result
      (period, draw_date, n1, n2, n3, n4, n5, n6, special, special_zodiac, source)
    VALUES
      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      draw_date=COALESCE(draw_result.draw_date, VALUES(draw_date)),
      n1=VALUES(n1), n2=VALUES(n2), n3=VALUES(n3),
      n4=VALUES(n4), n5=VALUES(n5), n6=VALUES(n6),
      special=VALUES(special),
      special_zodiac=VALUES(special_zodiac),
      source=VALUES(source)
    """
    with db_cursor() as cur:
        cur.execute(
            sql,
            (
                period,
                draw_date,
                numbers[0],
                numbers[1],
                numbers[2],
                numbers[3],
                numbers[4],
                numbers[5],
                special,
                special_zodiac,
                source,
            ),
        )


def list_draws(limit: int = 50) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT period, draw_date, n1, n2, n3, n4, n5, n6, special, special_zodiac, source
            FROM draw_result
            ORDER BY period DESC
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())


def list_draws_asc() -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT period, draw_date, n1, n2, n3, n4, n5, n6, special, special_zodiac
            FROM draw_result
            ORDER BY period ASC
            """
        )
        return list(cur.fetchall())


def latest_draw() -> dict[str, Any] | None:
    rows = list_draws(1)
    return rows[0] if rows else None


def insert_site_tip(
    *,
    period: int,
    site_code: str,
    page_url: str,
    raw_text: str,
    parsed_zodiacs: list[str],
    tip_type: str | None,
) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO site_tip
              (period, site_code, page_url, raw_text, parsed_zodiacs, tip_type)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                period,
                site_code,
                page_url[:500],
                raw_text,
                json.dumps(parsed_zodiacs, ensure_ascii=False),
                tip_type,
            ),
        )


def delete_tips_for_period(period: int) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM site_tip WHERE period=%s", (period,))


def list_tips(period: int) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, period, site_code, page_url, raw_text, parsed_zodiacs, tip_type, scraped_at
            FROM site_tip
            WHERE period=%s
            ORDER BY id DESC
            """,
            (period,),
        )
        rows = list(cur.fetchall())
        for r in rows:
            pz = r.get("parsed_zodiacs")
            if isinstance(pz, (bytes, bytearray)):
                pz = pz.decode("utf-8")
            if isinstance(pz, str):
                try:
                    r["parsed_zodiacs"] = json.loads(pz)
                except json.JSONDecodeError:
                    r["parsed_zodiacs"] = []
        return rows


def upsert_recommend(
    period: int, play_type: str, zodiac: str, score: float, detail: dict[str, Any]
) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO recommend_log (period, play_type, zodiac, score, score_detail)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              zodiac=VALUES(zodiac),
              score=VALUES(score),
              score_detail=VALUES(score_detail),
              created_at=CURRENT_TIMESTAMP
            """,
            (period, play_type, zodiac, score, json.dumps(detail, ensure_ascii=False)),
        )


def _parse_recommend_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    detail = row.get("score_detail")
    if isinstance(detail, (bytes, bytearray)):
        detail = detail.decode("utf-8")
    if isinstance(detail, str):
        try:
            row["score_detail"] = json.loads(detail)
        except json.JSONDecodeError:
            row["score_detail"] = {}
    return row


def get_recommends_for_period(period: int) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT period, play_type, zodiac, score, score_detail, hit, created_at
            FROM recommend_log
            WHERE period=%s
            """,
            (period,),
        )
        return [_parse_recommend_row(r) for r in cur.fetchall()]  # type: ignore[misc]


def list_recommends_pending_hit() -> list[dict[str, Any]]:
    """已有开奖、但 hit 仍为空的推荐行。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT r.period, r.play_type, r.zodiac, r.hit
            FROM recommend_log r
            INNER JOIN draw_result d ON d.period = r.period
            WHERE r.hit IS NULL
            ORDER BY r.period ASC
            """
        )
        return list(cur.fetchall())


def update_recommend_hit(period: int, play_type: str, hit: bool) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE recommend_log
            SET hit=%s
            WHERE period=%s AND play_type=%s
            """,
            (1 if hit else 0, period, play_type),
        )


def get_draw(period: int) -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT period, draw_date, n1, n2, n3, n4, n5, n6, special, special_zodiac, source
            FROM draw_result
            WHERE period=%s
            """,
            (period,),
        )
        return cur.fetchone()


def list_tip_periods_for_site_hits() -> list[int]:
    """有 tip 且已开奖、但尚未写入 site_tip_hit（任一玩法）的期号。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT t.period
            FROM site_tip t
            INNER JOIN draw_result d ON d.period = t.period
            WHERE NOT EXISTS (
              SELECT 1 FROM site_tip_hit h
              WHERE h.period = t.period
            )
            ORDER BY t.period ASC
            """
        )
        return [int(r["period"]) for r in cur.fetchall()]


def upsert_site_tip_hit(
    *,
    period: int,
    site_code: str,
    play_type: str,
    hit: bool,
    primary_zodiacs: list[str],
    tip_type: str | None,
) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO site_tip_hit
              (period, site_code, play_type, hit, primary_zodiacs, tip_type)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              hit=VALUES(hit),
              primary_zodiacs=VALUES(primary_zodiacs),
              tip_type=VALUES(tip_type),
              created_at=CURRENT_TIMESTAMP
            """,
            (
                period,
                site_code,
                play_type,
                1 if hit else 0,
                json.dumps(primary_zodiacs, ensure_ascii=False),
                tip_type,
            ),
        )


def site_hit_stats(
    play_type: str, *, before_period: int, window: int
) -> dict[str, dict[str, int]]:
    """各站在 before_period 之前近 window 期的命中统计。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT site_code, period, hit
            FROM site_tip_hit
            WHERE play_type=%s AND period < %s
            ORDER BY period DESC
            LIMIT %s
            """,
            (play_type, before_period, max(window * 30, 200)),
        )
        rows = list(cur.fetchall())
    per_site: dict[str, list[int]] = {}
    for r in rows:
        code = r["site_code"]
        bucket = per_site.setdefault(code, [])
        if len(bucket) >= window:
            continue
        bucket.append(int(r["hit"]))
    return {
        code: {"hits": sum(vals), "total": len(vals)}
        for code, vals in per_site.items()
    }


def list_recent_recommend_hits(limit: int = 20) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT r.period, r.play_type, r.zodiac, r.hit, r.score,
                   d.special_zodiac, d.special
            FROM recommend_log r
            LEFT JOIN draw_result d ON d.period = r.period
            ORDER BY r.period DESC, r.play_type
            LIMIT %s
            """,
            (limit,),
        )
        return list(cur.fetchall())


def latest_recommend_period() -> int | None:
    with db_cursor() as cur:
        cur.execute("SELECT MAX(period) AS p FROM recommend_log")
        row = cur.fetchone()
        return int(row["p"]) if row and row.get("p") is not None else None


def start_scrape_run(job_type: str) -> int:
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO scrape_run (job_type, status, message) VALUES (%s, 'running', %s)",
            (job_type, "进行中"),
        )
        return int(cur.lastrowid)


def finish_scrape_run(run_id: int, status: str, message: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE scrape_run
            SET status=%s, message=%s, finished_at=%s
            WHERE id=%s
            """,
            (status, message[:900], datetime.now(), run_id),
        )


def latest_scrape_run() -> dict[str, Any] | None:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, job_type, status, message, started_at, finished_at
            FROM scrape_run
            ORDER BY id DESC
            LIMIT 1
            """
        )
        return cur.fetchone()
