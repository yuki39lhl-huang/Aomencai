from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = "1234"
    db_name: str = "aomencai"

    # 历史开奖
    history_url: str = "https://amlskj-a.hopeojmpe.com:2088/amkjjl/2026.html"
    live_data_url: str = "https://amkj601-888.kjamzdsfdfdx.com/php/data.txt"

    # 站点入口（发现用）
    site_yanjiuyuan: str = "https://zrnilcrofy.690333hi.app:3216/#dh1"
    site_dinggeshui: str = "https://www.dinggeshui.com/"

    # 推荐页直连（经探测得到，失败时再走入口发现）
    tip_yanjiuyuan_main: str = "https://zrnilcrofy.690333hi.app:3216/main.html"
    tip_dinggeshui_jiuxiao: str = "https://333810.com/zl/%E4%B9%9D%E8%82%96.htm"
    tip_dinggeshui_home: str = "https://333810.com/"

    # 打分权重：偏遗漏
    weight_omit: float = 0.50
    weight_hot: float = 0.20
    weight_tip: float = 0.30
    hot_window: int = 30

    lunar_year: int = 2026


settings = Settings()
