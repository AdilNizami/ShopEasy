from notifications.infrastructure import models  # noqa: F401
from notifications.infrastructure.database import Base, engine

Base.metadata.create_all(bind=engine)
