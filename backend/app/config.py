from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    vision_api_key: str = ""
    vision_base_url: str = ""
    vision_model: str = ""
    webapp_url: str = ""
    database_path: str = str(ROOT / "data" / "fooddiary.db")
    cors_origins: str = "*"
    dev_user_id: int | None = None
    dev_user_name: str = "Dev User"
    # Comma-separated Telegram usernames without @
    allowed_usernames: str = "singullaris"


settings = Settings()
