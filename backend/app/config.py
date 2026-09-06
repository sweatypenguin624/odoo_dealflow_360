"""Application configuration.

Every tunable comes from the environment (or a local .env file). Nothing
here is a secret in source; see backend/.env.example for the full list.
"""

from functools import lru_cache
from typing import List, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- Runtime ----
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "DealFlow360 API"
    demo_mode: bool = False
    log_level: str = "INFO"
    log_json: bool = False

    # ---- Database ----
    database_url: str = "postgresql://postgres:postgres@localhost:5432/dealflow360"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # ---- Auth ----
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    password_reset_minutes: int = 60
    portal_token_hours: int = 168
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 300
    max_failed_logins_before_lock: int = 8
    account_lock_minutes: int = 15
    min_password_length: int = 10
    password_hash_rounds: int = 12

    # ---- Web ----
    frontend_url: str = "http://localhost:3000"
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])

    # ---- Email ----
    email_provider: Literal["console", "smtp", "disabled"] = "console"
    email_from: str = "DealFlow360 <no-reply@dealflow360.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True

    # ---- Payments ----
    payment_provider: Literal["manual"] = "manual"

    # ---- Business defaults ----
    default_currency: str = "USD"
    invoice_due_days: int = 14
    quote_valid_days: int = 30
    default_page_size: int = 25
    max_page_size: int = 100
    max_export_rows: int = 5000

    # ---- Deal health defaults (overridable in system settings) ----
    stall_threshold_days: int = 7
    discount_anomaly_multiplier: float = 1.5
    delivery_slippage_warning_days: int = 0
    delivery_slippage_critical_days: int = 5
    approval_aging_days: int = 3
    negotiation_aging_days: int = 5
    payment_overdue_grace_days: int = 0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
