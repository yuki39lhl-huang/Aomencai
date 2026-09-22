"""Fix MySQL table/column COMMENTs with UTF-8 (avoid PowerShell encoding issues)."""
from __future__ import annotations

import pymysql

from app.config import settings

STATEMENTS = [
    # draw_result
    "ALTER TABLE draw_result COMMENT='开奖结果表'",
    "ALTER TABLE draw_result MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID'",
    "ALTER TABLE draw_result MODIFY period INT UNSIGNED NOT NULL COMMENT '期号'",
    "ALTER TABLE draw_result MODIFY draw_date DATE NULL COMMENT '开奖日期'",
    "ALTER TABLE draw_result MODIFY n1 TINYINT UNSIGNED NOT NULL COMMENT '平码1'",
    "ALTER TABLE draw_result MODIFY n2 TINYINT UNSIGNED NOT NULL COMMENT '平码2'",
    "ALTER TABLE draw_result MODIFY n3 TINYINT UNSIGNED NOT NULL COMMENT '平码3'",
    "ALTER TABLE draw_result MODIFY n4 TINYINT UNSIGNED NOT NULL COMMENT '平码4'",
    "ALTER TABLE draw_result MODIFY n5 TINYINT UNSIGNED NOT NULL COMMENT '平码5'",
    "ALTER TABLE draw_result MODIFY n6 TINYINT UNSIGNED NOT NULL COMMENT '平码6'",
    "ALTER TABLE draw_result MODIFY special TINYINT UNSIGNED NOT NULL COMMENT '特码'",
    "ALTER TABLE draw_result MODIFY special_zodiac VARCHAR(8) NOT NULL COMMENT '特码对应生肖'",
    "ALTER TABLE draw_result MODIFY source VARCHAR(64) NOT NULL DEFAULT 'history' COMMENT '数据来源标识'",
    "ALTER TABLE draw_result MODIFY created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'",
    "ALTER TABLE draw_result MODIFY updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'",
    # site_tip
    "ALTER TABLE site_tip COMMENT='站点生肖推荐原文表'",
    "ALTER TABLE site_tip MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID'",
    "ALTER TABLE site_tip MODIFY period INT UNSIGNED NOT NULL COMMENT '对应期号'",
    "ALTER TABLE site_tip MODIFY site_code VARCHAR(32) NOT NULL COMMENT '站点编码：yanjiuyuan/dinggeshui'",
    "ALTER TABLE site_tip MODIFY page_url VARCHAR(512) NOT NULL COMMENT '抓取页面URL'",
    "ALTER TABLE site_tip MODIFY raw_text MEDIUMTEXT NOT NULL COMMENT '推荐原文'",
    "ALTER TABLE site_tip MODIFY parsed_zodiacs JSON NULL COMMENT '解析出的生肖列表JSON'",
    "ALTER TABLE site_tip MODIFY tip_type VARCHAR(32) NULL COMMENT '推荐类型：一肖/四肖/七肖/九肖等'",
    "ALTER TABLE site_tip MODIFY scraped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '抓取时间'",
    # recommend_log
    "ALTER TABLE recommend_log COMMENT='每期推荐快照（包肖/特码分行）'",
    "ALTER TABLE recommend_log MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID'",
    "ALTER TABLE recommend_log MODIFY period INT UNSIGNED NOT NULL COMMENT '预测期号'",
    "ALTER TABLE recommend_log MODIFY zodiac VARCHAR(8) NOT NULL COMMENT '该玩法最看好生肖'",
    "ALTER TABLE recommend_log MODIFY score DECIMAL(10, 4) NOT NULL COMMENT '综合得分'",
    "ALTER TABLE recommend_log MODIFY score_detail JSON NOT NULL COMMENT '分项得分详情JSON'",
    "ALTER TABLE recommend_log MODIFY created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间'",
    # scrape_run
    "ALTER TABLE scrape_run COMMENT='抓取运行日志表'",
    "ALTER TABLE scrape_run MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID'",
    "ALTER TABLE scrape_run MODIFY job_type VARCHAR(32) NOT NULL COMMENT '任务类型：bootstrap/refresh/history/tips'",
    "ALTER TABLE scrape_run MODIFY status VARCHAR(16) NOT NULL COMMENT '状态：running/success/failed'",
    "ALTER TABLE scrape_run MODIFY message VARCHAR(1000) NULL COMMENT '运行说明或错误信息'",
    "ALTER TABLE scrape_run MODIFY started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间'",
    "ALTER TABLE scrape_run MODIFY finished_at DATETIME NULL COMMENT '结束时间'",
]


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
    try:
        with conn.cursor() as cur:
            cur.execute("SET NAMES utf8mb4")
            for sql in STATEMENTS:
                cur.execute(sql)
            cur.execute(
                """
                SELECT TABLE_NAME, TABLE_COMMENT
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA=%s
                ORDER BY TABLE_NAME
                """,
                (settings.db_name,),
            )
            print("TABLE COMMENTS:")
            for name, comment in cur.fetchall():
                print(f"  {name}: {comment}")
            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_COMMENT
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA=%s
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                (settings.db_name,),
            )
            print("COLUMN COMMENTS:")
            for table, col, comment in cur.fetchall():
                print(f"  {table}.{col}: {comment}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
