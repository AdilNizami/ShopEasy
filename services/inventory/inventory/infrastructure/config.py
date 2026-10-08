from pydantic import Field
from service_common.settings import BaseServiceSettings


class InventorySettings(BaseServiceSettings):
    service_name: str = "inventory"
    reservation_ttl_seconds: int = Field(default=900, ge=30, le=86_400)


settings = InventorySettings()
