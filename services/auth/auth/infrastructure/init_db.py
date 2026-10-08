from auth.infrastructure import models  # noqa: F401
from auth.infrastructure.database import Base, engine

Base.metadata.create_all(bind=engine)
