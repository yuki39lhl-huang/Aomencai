"""为 site_tip 增加 play_scope，并按原文把已有资料归到包肖或特码。"""
from __future__ import annotations

import json

import pymysql

from app.config import settings
from app.scrapers.tips import play_scope_for_tip


def main() -> None:
    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as cur:
        cur.execute("SET NAMES utf8mb4")
        cur.execute(
            """
            SELECT COUNT(*) AS c FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME='site_tip' AND COLUMN_NAME='play_scope'
            """,
            (settings.db_name,),
        )
        if int(cur.fetchone()["c"]) == 0:
            cur.execute(
                """
                ALTER TABLE site_tip
                  ADD COLUMN play_scope VARCHAR(16) NULL
                  COMMENT '归属玩法：bao_xiao包肖 / te_ma特码，空表示混杂不参与打分'
                  AFTER tip_type
                """
            )
            print("added play_scope")
        else:
            print("play_scope exists")

        cur.execute("SELECT id, raw_text, tip_type, parsed_zodiacs FROM site_tip")
        rows = list(cur.fetchall())
        for row in rows:
            zodiacs = row.get("parsed_zodiacs")
            if isinstance(zodiacs, (bytes, bytearray)):
                zodiacs = zodiacs.decode("utf-8")
            if isinstance(zodiacs, str):
                try:
                    zodiacs = json.loads(zodiacs)
                except json.JSONDecodeError:
                    zodiacs = []
            scope = play_scope_for_tip(row.get("raw_text") or "", row.get("tip_type"), zodiacs or [])
            cur.execute("UPDATE site_tip SET play_scope=%s WHERE id=%s", (scope, row["id"]))
        cur.execute(
            """
            SELECT IFNULL(play_scope, 'none') AS scope, COUNT(*) AS n
            FROM site_tip GROUP BY play_scope
            """
        )
        print("backfill", list(cur.fetchall()))
    conn.close()
    print("migrate ok")


if __name__ == "__main__":
    main()
