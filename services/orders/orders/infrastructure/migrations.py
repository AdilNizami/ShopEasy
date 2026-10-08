from sqlalchemy import Engine, text


def ensure_order_owner_columns(engine: Engine) -> None:
    """Add ownership IDs to existing Orders tables within the Orders boundary."""
    statements = (
        "ALTER TABLE carts ADD COLUMN IF NOT EXISTS user_id UUID NULL",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS user_id UUID NULL",
        "CREATE INDEX IF NOT EXISTS ix_carts_user_id ON carts (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id)",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def ensure_inbox_correlation_column(engine: Engine) -> None:
    """Preserve trace correlation on event receipts for existing Orders databases."""
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE inbox_events ADD COLUMN IF NOT EXISTS correlation_id UUID NULL")
        )
