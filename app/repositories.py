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


def tip_first_seen_key(
    site_code: str,
    play_scope: str | None,
    tip_type: str | None,
    zodiacs: list[str] | tuple[str, ...],
) -> tuple[str, str, str, tuple[str, ...]]:
    """同一期、同一站、同一档名单。重复刷新用这个键保留第一次抓到的时间。"""
    return (
        str(site_code or ""),
        str(play_scope or ""),
        str(tip_type or ""),
        tuple(zodiacs or ()),
    )


def list_tip_first_seen(period: int) -> dict[tuple[str, str, str, tuple[str, ...]], datetime]:
    """删掉重抓之前，记下每份名单最早的 first_seen_at。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT site_code, play_scope, tip_type, parsed_zodiacs, first_seen_at, scraped_at
            FROM site_tip
            WHERE period=%s
            """,
            (period,),
        )
        rows = list(cur.fetchall())
    earliest: dict[tuple[str, str, str, tuple[str, ...]], datetime] = {}
    for row in rows:
        zodiacs = _load_zodiacs(row.get("parsed_zodiacs"))
        key = tip_first_seen_key(row.get("site_code"), row.get("play_scope"), row.get("tip_type"), zodiacs)
        seen = row.get("first_seen_at") or row.get("scraped_at")
        if not isinstance(seen, datetime):
            continue
        prev = earliest.get(key)
        if prev is None or seen < prev:
            earliest[key] = seen
    return earliest


def insert_site_tip(
    *,
    period: int,
    site_code: str,
    page_url: str,
    raw_text: str,
    parsed_zodiacs: list[str],
    tip_type: str | None,
    play_scope: str | None = None,
    first_seen_at: datetime | None = None,
) -> None:
    seen = first_seen_at or datetime.now()
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO site_tip
              (period, site_code, page_url, raw_text, parsed_zodiacs, tip_type, play_scope, scraped_at, first_seen_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                period,
                site_code,
                page_url[:500],
                raw_text,
                json.dumps(parsed_zodiacs, ensure_ascii=False),
                tip_type,
                play_scope,
                datetime.now(),
                seen,
            ),
        )


def delete_tips_for_period(period: int) -> None:
    with db_cursor() as cur:
        cur.execute("DELETE FROM site_tip WHERE period=%s", (period,))


def list_tips(period: int) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT id, period, site_code, page_url, raw_text, parsed_zodiacs, tip_type, play_scope,
                   scraped_at, first_seen_at
            FROM site_tip
            WHERE period=%s
            ORDER BY id DESC
            """,
            (period,),
        )
        rows = list(cur.fetchall())
        for r in rows:
            r["parsed_zodiacs"] = _load_zodiacs(r.get("parsed_zodiacs"))
        return rows


def list_tips_by_period() -> dict[int, list[dict[str, Any]]]:
    """全部资料按期号分组，供滚动回测一次取出。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT period, site_code, raw_text, parsed_zodiacs, tip_type, play_scope,
                   scraped_at, first_seen_at
            FROM site_tip
            ORDER BY period ASC, id ASC
            """
        )
        rows = list(cur.fetchall())
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        row["parsed_zodiacs"] = _load_zodiacs(row.get("parsed_zodiacs"))
        grouped.setdefault(int(row["period"]), []).append(row)
    return grouped


def _load_zodiacs(value: Any) -> list[str]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def ensure_backtest_table() -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS backtest_snapshot (
              id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
              through_period INT UNSIGNED NOT NULL COMMENT '回测用到的最新已开奖期',
              payload JSON NOT NULL COMMENT '对照结果',
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '写入时间',
              PRIMARY KEY (id),
              KEY idx_through_period (through_period)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='滚动回测快照。不改推荐，不改权重'
            """
        )


def save_backtest_snapshot(through_period: int, payload: dict[str, Any]) -> None:
    ensure_backtest_table()
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO backtest_snapshot (through_period, payload)
            VALUES (%s, %s)
            """,
            (through_period, json.dumps(payload, ensure_ascii=False)),
        )


def latest_backtest_snapshot() -> dict[str, Any] | None:
    ensure_backtest_table()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT through_period, payload, created_at
            FROM backtest_snapshot
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
    if not row:
        return None
    payload = row.get("payload")
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        payload = json.loads(payload)
    created = row.get("created_at")
    saved_at = created.strftime("%Y-%m-%d %H:%M") if isinstance(created, datetime) else None
    if isinstance(payload, dict):
        payload = {**payload, "saved_at": saved_at}
    return payload


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


def list_drawn_tip_periods() -> list[int]:
    """已有开奖、且存了资料的期号。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT t.period
            FROM site_tip t
            INNER JOIN draw_result d ON d.period = t.period
            ORDER BY t.period ASC
            """
        )
        return [int(r["period"]) for r in cur.fetchall()]


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
    list_hit: bool | None = None,
) -> None:
    """写入站点对账。已有行的 hit（只荐一肖）不覆盖，只补名单覆盖。"""
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO site_tip_hit
              (period, site_code, play_type, hit, list_hit, primary_zodiacs, tip_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              list_hit=VALUES(list_hit),
              primary_zodiacs=VALUES(primary_zodiacs),
              tip_type=VALUES(tip_type)
            """,
            (
                period,
                site_code,
                play_type,
                1 if hit else 0,
                None if list_hit is None else (1 if list_hit else 0),
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
