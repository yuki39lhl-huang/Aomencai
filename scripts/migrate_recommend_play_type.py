"""为 recommend_log 增加 play_type，支持同存包肖/特码两套推荐。"""
from __future__ import annotations

import pymysql

from app.config import settings


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
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME='recommend_log' AND COLUMN_NAME='play_type'
            """,
            (settings.db_name,),
        )
        exists = cur.fetchone()[0] > 0
        if not exists:
            cur.execute(
                """
                ALTER TABLE recommend_log
                  ADD COLUMN play_type VARCHAR(16) NOT NULL DEFAULT 'bao_xiao'
                  COMMENT '玩法：bao_xiao包肖 / te_ma特码生肖'
                  AFTER period
                """
            )
            print("added play_type")
        # 去掉旧唯一键，改为 (period, play_type)
        cur.execute("SHOW INDEX FROM recommend_log WHERE Key_name='uk_period'")
        if cur.fetchall():
            cur.execute("ALTER TABLE recommend_log DROP INDEX uk_period")
            print("dropped uk_period")
        cur.execute("SHOW INDEX FROM recommend_log WHERE Key_name='uk_period_play'")
        if not cur.fetchall():
            cur.execute(
                "ALTER TABLE recommend_log ADD UNIQUE KEY uk_period_play (period, play_type)"
            )
            print("added uk_period_play")
        # 旧数据默认当包肖；注释刷新
        cur.execute(
            "ALTER TABLE recommend_log MODIFY zodiac VARCHAR(8) NOT NULL COMMENT '该玩法最看好生肖'"
        )
        cur.execute("ALTER TABLE recommend_log COMMENT='每期推荐快照（包肖/特码分行）'")
    conn.close()
    print("migrate ok")


if __name__ == "__main__":
    main()
