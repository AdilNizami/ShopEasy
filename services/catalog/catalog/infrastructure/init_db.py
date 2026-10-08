from catalog.infrastructure import models  # noqa: F401
from catalog.infrastructure.database import Base, engine

Base.metadata.create_all(bind=engine)
