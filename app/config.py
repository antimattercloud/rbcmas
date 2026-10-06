from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    app_name: str = "Research Building Chemical Management & Accountability System"
    app_short_name: str = "RBCMAS"
    creator_name: str = "Ditij M. Dhameliya"
    footer_text: str = "Developed by DM. Dhameliya"

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'rbcmas.db').as_posix()}"
    secret_key: str = "dev-only-insecure-secret-key-change-me"
    session_hours: int = 12

    expiry_warning_days_1: int = 30
    expiry_warning_days_2: int = 60
    expiry_warning_days_3: int = 90
    dead_stock_days: int = 365
    variance_tolerance_percent: float = 1.0

    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
