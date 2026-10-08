from service_common.settings import BaseServiceSettings


class PaymentsSettings(BaseServiceSettings):
    service_name: str = "payments"
    orders_base_url: str = "http://orders:8000"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq/"
    messaging_enabled: bool = False


settings = PaymentsSettings()
