from fastapi import FastAPI
from service_common.http import (
    CorrelationIdMiddleware,
    install_error_handlers,
    install_health_routes,
)
from service_common.logging import configure_logging

from catalog.api.router import categories_router, products_router
from catalog.infrastructure.config import settings
from catalog.infrastructure.database import SessionLocal

configure_logging(settings.log_level)
app = FastAPI(title="ShopEasy Catalog", version="1.0.0")
app.add_middleware(CorrelationIdMiddleware)
install_error_handlers(app)
install_health_routes(app, settings.service_name, SessionLocal)
app.include_router(products_router, prefix="/v1")
app.include_router(categories_router, prefix="/v1")
