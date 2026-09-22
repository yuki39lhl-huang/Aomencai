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
            SELECT period, play_type, zodiac, score, score_detail, created_at
            FROM recommend_log
            WHERE period=%s
            """,
            (period,),
        )
        return [_parse_recommend_row(r) for r in cur.fetchall()]  # type: ignore[misc]


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
