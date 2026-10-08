from inventory.infrastructure import models  # noqa: F401
from inventory.infrastructure.database import Base, engine

Base.metadata.create_all(bind=engine)
