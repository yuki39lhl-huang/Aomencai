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

        if not _table_exists(cur, "site_tip_hit"):
            cur.execute(
                """
                CREATE TABLE site_tip_hit (
                  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                  period INT UNSIGNED NOT NULL COMMENT '期号',
                  site_code VARCHAR(32) NOT NULL COMMENT '站点编码',
                  play_type VARCHAR(16) NOT NULL COMMENT '玩法：bao_xiao / te_ma',
                  hit TINYINT NOT NULL COMMENT '1中 0否',
                  primary_zodiacs JSON NULL COMMENT '该站当期主推生肖',
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
    print("migrate ok")


if __name__ == "__main__":
    main()
