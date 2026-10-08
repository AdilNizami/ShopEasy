from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=False, env_prefix="GATEWAY_"
    )

    service_name: str = "gateway"
    log_level: str = "INFO"
    upstream_timeout_seconds: float = 3.0
    connect_timeout_seconds: float = 1.0
    frontend_origins: str = "http://localhost:3000"
    catalog_url: str = "http://catalog:8000"
    orders_url: str = "http://orders:8000"
    payments_url: str = "http://payments:8000"
    inventory_url: str = "http://inventory:8000"
    auth_url: str = "http://auth:8000"
    notifications_url: str = "http://notifications:8000"
    rabbitmq_management_url: str = "http://rabbitmq:15672"
    rabbitmq_user: str = "shop_easy"
    rabbitmq_password: str = ""

    @property
    def service_urls(self) -> dict[str, str]:
        return {
            "catalog": self.catalog_url,
            "orders": self.orders_url,
            "payments": self.payments_url,
            "inventory": self.inventory_url,
            "auth": self.auth_url,
            "notifications": self.notifications_url,
        }


settings = GatewaySettings()
