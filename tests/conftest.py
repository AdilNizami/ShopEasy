import os

for service in ("catalog", "orders", "payments", "inventory"):
    os.environ.setdefault(
        f"{service.upper()}_DATABASE_URL",
        f"postgresql+psycopg://{service}:test@localhost:5432/{service}",
    )

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("AUTH_DATABASE_URL", "postgresql+psycopg://auth:test@localhost:5432/auth")
os.environ.setdefault("AUTH_JWT_SECRET", "test-only-signing-secret-with-at-least-32-bytes")
