from service_common.settings import BaseServiceSettings


class NotificationsSettings(BaseServiceSettings):
    service_name: str = "notifications"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq/"
    event_queue_name: str = "notifications.events.v1"
    messaging_enabled: bool = False


settings = NotificationsSettings()
