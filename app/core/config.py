from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file_path: str = Field(default="var/log/flight-alerts/app.log", alias="LOG_FILE_PATH")
    database_url: str = Field(alias="DATABASE_URL")
    admin_api_token: str = Field(default="change-me", alias="ADMIN_API_TOKEN")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_allowed_user_ids: str = Field(alias="TELEGRAM_ALLOWED_USER_IDS")

    travelpayouts_api_token: str = Field(alias="TRAVELPAYOUTS_API_TOKEN")
    travelpayouts_base_url: str = Field(default="https://api.travelpayouts.com", alias="TRAVELPAYOUTS_BASE_URL")
    travelpayouts_locale: str = Field(default="ru", alias="TRAVELPAYOUTS_LOCALE")
    travelpayouts_default_market: str = Field(default="ru", alias="TRAVELPAYOUTS_DEFAULT_MARKET")
    travelpayouts_default_currency: str = Field(default="RUB", alias="TRAVELPAYOUTS_DEFAULT_CURRENCY")

    http_timeout_seconds: float = Field(default=10.0, alias="HTTP_TIMEOUT_SECONDS")
    http_max_retries: int = Field(default=3, alias="HTTP_MAX_RETRIES")
    http_retry_backoff_seconds: float = Field(default=1.5, alias="HTTP_RETRY_BACKOFF_SECONDS")

    default_check_interval_minutes: int = Field(default=60, alias="DEFAULT_CHECK_INTERVAL_MINUTES")
    scheduler_tick_seconds: int = Field(default=60, alias="SCHEDULER_TICK_SECONDS")
    max_concurrent_checks: int = Field(default=3, alias="MAX_CONCURRENT_CHECKS")
    search_cache_ttl_seconds: int = Field(default=1800, alias="SEARCH_CACHE_TTL_SECONDS")
    alert_cooldown_hours: int = Field(default=12, alias="ALERT_COOLDOWN_HOURS")
    min_price_drop_abs: int = Field(default=500, alias="MIN_PRICE_DROP_ABS")
    min_price_drop_pct: int = Field(default=5, alias="MIN_PRICE_DROP_PCT")

    @computed_field
    @property
    def allowed_user_ids(self) -> set[int]:
        return {int(item.strip()) for item in self.telegram_allowed_user_ids.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
