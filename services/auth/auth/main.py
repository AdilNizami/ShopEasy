from fastapi import FastAPI
from service_common.http import (
    CorrelationIdMiddleware,
    install_error_handlers,
    install_health_routes,
)
from service_common.logging import configure_logging

from auth.api.router import router
from auth.infrastructure.database import SessionLocal
from auth.settings import settings

configure_logging(settings.log_level)

app = FastAPI(title="ShopEasy Authentication", version="1.0.0")
app.add_middleware(CorrelationIdMiddleware)
install_error_handlers(app)
install_health_routes(app, settings.service_name, SessionLocal)
app.include_router(router, prefix="/v1")
