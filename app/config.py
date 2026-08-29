from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = ROOT_DIR / "sessions"
MEDIA_DIR = ROOT_DIR / "data" / "media"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    admin_ids: str

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "newsletter"
    mysql_password: str = "newsletter"
    mysql_database: str = "newsletter"

    telegram_api_id: int
    telegram_api_hash: str

    send_delay_seconds: float = 4.0

    @property
    def admin_id_list(self) -> list[int]:
        return [int(item.strip()) for item in self.admin_ids.split(",") if item.strip()]

    @property
    def database_url(self) -> str:
        password = quote_plus(self.mysql_password)
        return (
            f"mysql+aiomysql://{self.mysql_user}:{password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
