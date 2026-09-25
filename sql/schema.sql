-- aomencai 库已存在，本脚本仅建表，不创建/删除数据库
USE aomencai;

CREATE TABLE IF NOT EXISTS draw_result (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  period INT UNSIGNED NOT NULL COMMENT '期号',
  draw_date DATE NULL COMMENT '开奖日期',
  n1 TINYINT UNSIGNED NOT NULL COMMENT '平码1',
  n2 TINYINT UNSIGNED NOT NULL COMMENT '平码2',
  n3 TINYINT UNSIGNED NOT NULL COMMENT '平码3',
  n4 TINYINT UNSIGNED NOT NULL COMMENT '平码4',
  n5 TINYINT UNSIGNED NOT NULL COMMENT '平码5',
  n6 TINYINT UNSIGNED NOT NULL COMMENT '平码6',
  special TINYINT UNSIGNED NOT NULL COMMENT '特码',
  special_zodiac VARCHAR(8) NOT NULL COMMENT '特码对应生肖',
  source VARCHAR(64) NOT NULL DEFAULT 'history' COMMENT '数据来源标识',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_period (period),
  KEY idx_draw_date (draw_date),
  KEY idx_special_zodiac (special_zodiac)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='开奖结果表';

CREATE TABLE IF NOT EXISTS site_tip (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  period INT UNSIGNED NOT NULL COMMENT '对应期号',
  site_code VARCHAR(32) NOT NULL COMMENT '站点编码：yanjiuyuan/dinggeshui',
  page_url VARCHAR(512) NOT NULL COMMENT '抓取页面URL',
  raw_text MEDIUMTEXT NOT NULL COMMENT '推荐原文',
  parsed_zodiacs JSON NULL COMMENT '解析出的生肖列表JSON',
  tip_type VARCHAR(32) NULL COMMENT '推荐类型：一肖/四肖/七肖/九肖等',
  scraped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '抓取时间',
  PRIMARY KEY (id),
  KEY idx_period_site (period, site_code),
  KEY idx_scraped_at (scraped_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='站点生肖推荐原文表';

CREATE TABLE IF NOT EXISTS recommend_log (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  period INT UNSIGNED NOT NULL COMMENT '预测期号',
  play_type VARCHAR(16) NOT NULL DEFAULT 'bao_xiao' COMMENT '玩法：bao_xiao包肖 / te_ma特码生肖',
  zodiac VARCHAR(8) NOT NULL COMMENT '该玩法最看好生肖',
  score DECIMAL(10, 4) NOT NULL COMMENT '综合得分',
  score_detail JSON NOT NULL COMMENT '分项得分详情JSON',
  hit TINYINT NULL DEFAULT NULL COMMENT '对账：NULL未开奖 1中 0否',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '生成时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_period_play (period, play_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='每期推荐快照（包肖/特码分行）';

CREATE TABLE IF NOT EXISTS site_tip_hit (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='站点推荐按玩法对账';

CREATE TABLE IF NOT EXISTS scrape_run (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  job_type VARCHAR(32) NOT NULL COMMENT '任务类型：bootstrap/refresh/history/tips',
  status VARCHAR(16) NOT NULL COMMENT '状态：running/success/failed',
  message VARCHAR(1000) NULL COMMENT '运行说明或错误信息',
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '开始时间',
  finished_at DATETIME NULL COMMENT '结束时间',
  PRIMARY KEY (id),
  KEY idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='抓取运行日志表';
