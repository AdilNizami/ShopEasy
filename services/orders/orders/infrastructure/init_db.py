from orders.infrastructure.migrations import (
    ensure_inbox_correlation_column,
    ensure_order_owner_columns,
)
from service_common.outbox_migration import ensure_outbox_status_columns

from orders.infrastructure import models  # noqa: F401
from orders.infrastructure.database import Base, engine

Base.metadata.create_all(bind=engine)
ensure_outbox_status_columns(engine)
ensure_order_owner_columns(engine)
ensure_inbox_correlation_column(engine)
