from fastapi import FastAPI
from service_common.http import (
    CorrelationIdMiddleware,
    install_error_handlers,
    install_health_routes,
)
from service_common.logging import configure_logging

from inventory.api.router import router
from inventory.infrastructure.config import settings
from inventory.infrastructure.database import SessionLocal

configure_logging(settings.log_level)
app = FastAPI(title="ShopEasy Inventory", version="1.0.0")
app.add_middleware(CorrelationIdMiddleware)
install_error_handlers(app)
install_health_routes(app, settings.service_name, SessionLocal)
app.include_router(router, prefix="/v1")
