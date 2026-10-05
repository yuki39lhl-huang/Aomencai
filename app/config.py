from pydantic_settings import BaseSettings, SettingsConfigDict

from app.sites import HISTORY_SOURCE, LIVE_SOURCE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = "1234"
    db_name: str = "aomencai"

    # 开奖源默认取 app.sites 配置；可用环境变量覆盖
    history_url: str = HISTORY_SOURCE.url
    live_data_url: str = LIVE_SOURCE.url

    # 打分权重：包肖资料只占 0.15，用来微调；特码资料不进排名
    weight_omit: float = 0.50
    weight_hot: float = 0.20
    weight_tip: float = 0.15
    hot_window: int = 30
    # 热度领先不足这么多（次）时，热度全体记 0，避免 19 次和 18 次拉开满分
    score_min_lead: int = 3
    # 遗漏分在典型间隔附近最高，离得越远越低。特码平均大约 12 期开一次，
    # 包肖平均大约隔几期才整期不见。不再把“最冷”自动当成第一，避免一个生肖连挂几十期。
    bao_omit_center: int = 4
    bao_omit_half: int = 4
    tema_omit_center: int = 12
    tema_omit_half: int = 12
    tema_hot_full: int = 6

    # 站点命中率降权：近 N 期相对期望命中率映射到权重区间
    site_hit_window: int = 20
    site_weight_floor: float = 0.25
    site_weight_ceil: float = 1.25
    # 单肖包肖 / 特码经验期望（用于相对降权，非绝对准确率）
    expected_hit_bao: float = 0.42
    expected_hit_tema: float = 0.09

    lunar_year: int = 2026


settings = Settings()
