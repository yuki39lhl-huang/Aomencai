-- 可选：手工重建表（会清空数据）。默认流程不要执行本文件。
-- 执行后请再跑：mysql -uroot -p1234 aomencai < sql/schema.sql
USE aomencai;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS recommend_log;
DROP TABLE IF EXISTS site_tip;
DROP TABLE IF EXISTS scrape_run;
DROP TABLE IF EXISTS draw_result;
SET FOREIGN_KEY_CHECKS = 1;
