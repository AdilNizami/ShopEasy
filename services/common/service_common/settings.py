from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    service_name: str
    database_url: str
    log_level: str = "INFO"
    downstream_timeout_seconds: float = 2.0
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_reset_seconds: float = 10.0
