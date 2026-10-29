from __future__ import annotations

import json
from datetime import date, datetime, timedelta
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
      special_zodiac=IF(
        draw_result.source='history' AND VALUES(source)='live',
        draw_result.special_zodiac,
        VALUES(special_zodiac)
      ),
      source=IF(
        draw_result.source='history' AND VALUES(source)='live',
        draw_result.source,
        VALUES(source)
      )
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
    """重抓替换之前，记下每份名单最早的 first_seen_at。"""
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


def replace_site_tips(period: int, rows_by_site: dict[str, list[dict[str, Any]]]) -> None:
    """一个事务里按站替换本期名单。不在 rows_by_site 里的站，旧名单原样保留。"""
    if not rows_by_site:
        return
    now = datetime.now()
    with db_cursor() as cur:
        for site_code, rows in rows_by_site.items():
            cur.execute(
                "DELETE FROM site_tip WHERE period=%s AND site_code=%s", (period, site_code)
            )
            cur.executemany(
                """
                INSERT INTO site_tip
                  (period, site_code, page_url, raw_text, parsed_zodiacs, tip_type, play_scope,
                   scraped_at, first_seen_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        period,
                        site_code,
                        str(row["page_url"])[:500],
                        row["raw_text"],
                        json.dumps(row["parsed_zodiacs"], ensure_ascii=False),
                        row.get("tip_type"),
                        row.get("play_scope"),
                        now,
                        row.get("first_seen_at") or now,
                    )
                    for row in rows
                ],
            )


def ensure_site_scrape_table() -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS site_scrape_status (
              site_code VARCHAR(32) NOT NULL COMMENT '站点代号',
              fail_streak INT NOT NULL DEFAULT 0 COMMENT '连续没抓到名单的期数',
              last_reason VARCHAR(32) NULL COMMENT '最近一次失败原因',
              last_detail VARCHAR(300) NULL COMMENT '最近一次失败说明',
              last_period INT NULL COMMENT '最近一次记录的期号',
              last_fail_period INT NULL COMMENT '最近一次失败计入连击的期号',
              updated_at DATETIME NOT NULL COMMENT '最近更新时间',
              PRIMARY KEY (site_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
              COMMENT='站点抓取成败。连续失败只用于面板告警，不改打分权重'
            """
        )
        cur.execute("SHOW COLUMNS FROM site_scrape_status")
        cols = {str(row["Field"]) for row in cur.fetchall()}
        if "last_period" not in cols:
            cur.execute(
                "ALTER TABLE site_scrape_status ADD COLUMN last_period INT NULL COMMENT '最近一次记录的期号' AFTER last_detail"
            )
        if "last_fail_period" not in cols:
            cur.execute(
                "ALTER TABLE site_scrape_status ADD COLUMN last_fail_period INT NULL COMMENT '最近一次失败计入连击的期号' AFTER last_period"
            )


def record_site_scrape(
    site_code: str,
    *,
    ok: bool,
    period: int | None = None,
    reason: str | None = None,
    detail: str | None = None,
    had_prior_tips: bool = False,
) -> dict[str, Any]:
    """成功清零。失败按期号去重累加。同一期重复刷新不把连击再加一。"""
    ensure_site_scrape_table()
    now = datetime.now()
    short = (detail or "")[:300] or None
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT fail_streak, last_reason, last_period, last_fail_period
            FROM site_scrape_status WHERE site_code=%s
            """,
            (site_code,),
        )
        prev = cur.fetchone() or {}
        if ok:
            cur.execute(
                """
                INSERT INTO site_scrape_status
                  (site_code, fail_streak, last_reason, last_detail, last_period, last_fail_period, updated_at)
                VALUES (%s, 0, NULL, NULL, %s, NULL, %s)
                ON DUPLICATE KEY UPDATE
                  fail_streak=0, last_reason=NULL, last_detail=NULL,
                  last_period=VALUES(last_period), last_fail_period=NULL,
                  updated_at=VALUES(updated_at)
                """,
                (site_code, period, now),
            )
            streak = 0
            saved_reason = None
            counted = False
        else:
            last_fail_period = prev.get("last_fail_period")
            same_period = (
                period is not None
                and last_fail_period is not None
                and int(last_fail_period) == int(period)
            )
            streak = int(prev.get("fail_streak") or 0)
            if same_period:
                counted = False
            else:
                streak += 1
                counted = True
            cur.execute(
                """
                INSERT INTO site_scrape_status
                  (site_code, fail_streak, last_reason, last_detail, last_period, last_fail_period, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  fail_streak=%s,
                  last_reason=VALUES(last_reason),
                  last_detail=VALUES(last_detail),
                  last_period=VALUES(last_period),
                  last_fail_period=VALUES(last_fail_period),
                  updated_at=VALUES(updated_at)
                """,
                (
                    site_code,
                    streak,
                    reason,
                    short,
                    period,
                    period if counted or last_fail_period is None else last_fail_period,
                    now,
                    streak,
                ),
            )
            saved_reason = reason or prev.get("last_reason")
    if ok:
        reuse = None
    elif had_prior_tips:
        reuse = "same_period"
    else:
        reuse = "prior_period"
    return {
        "site_code": site_code,
        "fail_streak": streak,
        "reason": saved_reason,
        "alert": streak >= 3,
        "counted": counted if not ok else False,
        "reuse": reuse,
    }


def list_site_alerts() -> list[dict[str, Any]]:
    ensure_site_scrape_table()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT site_code, fail_streak, last_reason, last_detail, last_period, last_fail_period, updated_at
            FROM site_scrape_status
            WHERE fail_streak >= 3
            ORDER BY fail_streak DESC, site_code
            """
        )
        return list(cur.fetchall())


def list_locked_bao_missing_lian() -> list[dict[str, Any]]:
    """已有中没中、但缺三连肖或五连肖的单肖。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT b.period, b.zodiac, b.score, b.score_detail, b.hit,
                   l3.zodiacs AS lian3_zodiacs,
                   l5.period AS lian5_period
            FROM recommend_log b
            LEFT JOIN recommend_log l3
              ON l3.period = b.period AND l3.play_type = 'lian3'
            LEFT JOIN recommend_log l5
              ON l5.period = b.period AND l5.play_type = 'lian5'
            WHERE b.play_type = 'bao_xiao'
              AND b.hit IS NOT NULL
              AND (l3.period IS NULL OR l5.period IS NULL)
            ORDER BY b.period
            """
        )
        rows = list(cur.fetchall())
    for row in rows:
        row["score_detail"] = _parse_detail(row.get("score_detail"))
        row["lian3_zodiacs"] = _load_zodiacs(row.get("lian3_zodiacs")) or None
    return rows


def _parse_detail(value: Any) -> dict[str, Any]:
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


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


_SNAPSHOT_KEEP = 8


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
        cur.execute(
            """
            DELETE FROM backtest_snapshot
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id FROM backtest_snapshot ORDER BY id DESC LIMIT %s
                ) AS kept
            )
            """,
            (_SNAPSHOT_KEEP,),
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
    period: int,
    play_type: str,
    zodiac: str,
    score: float,
    detail: dict[str, Any],
    zodiacs: list[str] | None = None,
) -> None:
    """写入或覆盖一期一个玩法的推荐。不碰 hit，已对账的结果由调用方先判断锁定。"""
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO recommend_log
              (period, play_type, zodiac, zodiacs, score, score_detail)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              zodiac=VALUES(zodiac),
              zodiacs=VALUES(zodiacs),
              score=VALUES(score),
              score_detail=VALUES(score_detail),
              created_at=CURRENT_TIMESTAMP
            """,
            (
                period,
                play_type,
                zodiac,
                json.dumps(zodiacs, ensure_ascii=False) if zodiacs else None,
                score,
                json.dumps(detail, ensure_ascii=False),
            ),
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
    if "zodiacs" in row:
        row["zodiacs"] = _load_zodiacs(row.get("zodiacs")) or None
    return row


def get_recommends_for_period(period: int) -> list[dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT period, play_type, zodiac, zodiacs, score, score_detail, hit, created_at
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


def list_recent_recommend_hits(periods: int = 20) -> list[dict[str, Any]]:
    """最近 periods 期的全部玩法推荐。按期数截取，玩法多了也不会少显示几期。"""
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT r.period, r.play_type, r.zodiac, r.zodiacs,
                   r.hit, r.score, d.special_zodiac, d.special
            FROM recommend_log r
            INNER JOIN (
              SELECT DISTINCT period FROM recommend_log ORDER BY period DESC LIMIT %s
            ) recent ON recent.period = r.period
            LEFT JOIN draw_result d ON d.period = r.period
            ORDER BY r.period DESC, r.play_type
            """,
            (periods,),
        )
        rows = list(cur.fetchall())
    for row in rows:
        row["zodiacs"] = _load_zodiacs(row.get("zodiacs")) or None
    return rows


def latest_recommend_period() -> int | None:
    with db_cursor() as cur:
        cur.execute("SELECT MAX(period) AS p FROM recommend_log")
        row = cur.fetchone()
        return int(row["p"]) if row and row.get("p") is not None else None


def expire_stale_scrape_runs(*, max_minutes: int = 30) -> int:
    """把长时间仍是 running 的任务标成失败，避免占坑。"""
    now = datetime.now()
    cutoff = now - timedelta(minutes=max_minutes)
    with db_cursor() as cur:
        cur.execute(
            """
            UPDATE scrape_run
            SET status='failed',
                message=%s,
                finished_at=%s
            WHERE status='running'
              AND started_at < %s
            """,
            (
                f"超时未结束（超过 {max_minutes} 分钟），已自动清理",
                now,
                cutoff,
            ),
        )
        return int(cur.rowcount or 0)


def start_scrape_run(job_type: str) -> int:
    expire_stale_scrape_runs()
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
