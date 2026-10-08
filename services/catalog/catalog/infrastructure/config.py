from service_common.settings import BaseServiceSettings


class CatalogSettings(BaseServiceSettings):
    service_name: str = "catalog"


settings = CatalogSettings()
