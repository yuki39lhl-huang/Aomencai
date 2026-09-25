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

    # 打分权重：偏遗漏
    weight_omit: float = 0.50
    weight_hot: float = 0.20
    weight_tip: float = 0.30
    hot_window: int = 30

    lunar_year: int = 2026


settings = Settings()
