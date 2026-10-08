from service_common.settings import BaseServiceSettings


class OrdersSettings(BaseServiceSettings):
    service_name: str = "orders"
    catalog_base_url: str = "http://catalog:8000"
    inventory_base_url: str = "http://inventory:8000"
    payments_base_url: str = "http://payments:8000"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq/"
    event_queue_name: str = "orders.events.v1"
    messaging_enabled: bool = False


settings = OrdersSettings()
