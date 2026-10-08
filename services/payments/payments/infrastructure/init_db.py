from service_common.outbox_migration import ensure_outbox_status_columns

from payments.infrastructure import models  # noqa: F401
from payments.infrastructure.database import Base, engine

Base.metadata.create_all(bind=engine)
ensure_outbox_status_columns(engine)
