"""为对账与站点降权增加 hit 字段 / site_tip_hit 表。"""
from __future__ import annotations

import pymysql

from app.config import settings


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
        """,
        (settings.db_name, table, column),
    )
    row = cur.fetchone()
    return int(row[0] if not isinstance(row, dict) else row["c"]) > 0


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        """,
        (settings.db_name, table),
    )
    row = cur.fetchone()
    return int(row[0] if not isinstance(row, dict) else row["c"]) > 0


def main() -> None:
    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        autocommit=True,
    )
    with conn.cursor() as cur:
        cur.execute("SET NAMES utf8mb4")
        if not _column_exists(cur, "recommend_log", "hit"):
            cur.execute(
                """
                ALTER TABLE recommend_log
                  ADD COLUMN hit TINYINT NULL DEFAULT NULL
                  COMMENT '对账：NULL未开奖 1中 0否'
                  AFTER score_detail
                """
            )
            print("added recommend_log.hit")
        else:
            print("recommend_log.hit exists")

        if _table_exists(cur, "site_tip_hit") and not _column_exists(cur, "site_tip_hit", "list_hit"):
            cur.execute(
                """
                ALTER TABLE site_tip_hit
                  ADD COLUMN list_hit TINYINT NULL DEFAULT NULL
                  COMMENT '名单覆盖：开奖生肖落在完整名单里为 1，否则 0。不参与站点权重'
                  AFTER hit
                """
            )
            print("added site_tip_hit.list_hit")
        elif _table_exists(cur, "site_tip_hit"):
            print("site_tip_hit.list_hit exists")

        if _table_exists(cur, "site_tip") and not _column_exists(cur, "site_tip", "first_seen_at"):
            cur.execute(
                """
                ALTER TABLE site_tip
                  ADD COLUMN first_seen_at DATETIME NULL DEFAULT NULL
                  COMMENT '第一次抓到这份名单的时间。重复刷新不改。回测只采用早于开奖21:32的记录'
                  AFTER scraped_at
                """
            )
            cur.execute(
                "UPDATE site_tip SET first_seen_at = scraped_at WHERE first_seen_at IS NULL"
            )
            print("added site_tip.first_seen_at")
        elif _table_exists(cur, "site_tip"):
            print("site_tip.first_seen_at exists")

        if not _table_exists(cur, "site_tip_hit"):
            cur.execute(
                """
                CREATE TABLE site_tip_hit (
                  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                  period INT UNSIGNED NOT NULL COMMENT '期号',
                  site_code VARCHAR(32) NOT NULL COMMENT '站点编码',
                  play_type VARCHAR(16) NOT NULL COMMENT '玩法：bao_xiao / te_ma',
                  hit TINYINT NOT NULL COMMENT '只荐一肖：名单第一个生肖是否命中。站点权重只用这一列',
                  list_hit TINYINT NULL DEFAULT NULL COMMENT '名单覆盖：开奖生肖落在完整名单里为 1，否则 0。不参与站点权重',
                  primary_zodiacs JSON NULL COMMENT '该站当期主推的完整生肖名单',
                  tip_type VARCHAR(32) NULL COMMENT '主推类型',
                  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '对账时间',
                  PRIMARY KEY (id),
                  UNIQUE KEY uk_period_site_play (period, site_code, play_type),
                  KEY idx_site_play_period (site_code, play_type, period)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                COMMENT='站点推荐按玩法对账'
                """
            )
            print("created site_tip_hit")
        else:
            print("site_tip_hit exists")
    conn.close()
    from app.services.reconcile import backfill_list_hits

    filled = backfill_list_hits()
    print(f"list_hit backfill rows={filled}")
    print("migrate ok")


if __name__ == "__main__":
    main()
