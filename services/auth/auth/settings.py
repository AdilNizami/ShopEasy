from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False, env_prefix="AUTH_")

    service_name: str = "auth"
    database_url: str
    log_level: str = "INFO"
    access_token_ttl_seconds: int = Field(default=900, gt=0, le=86_400)
    engineering_operator_ids: str = ""


settings = AuthSettings()
