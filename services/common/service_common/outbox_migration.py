"""Small forward-compatible bootstrap for outbox columns added after Phase 4."""

from sqlalchemy import Engine, text


def ensure_outbox_status_columns(engine: Engine) -> None:
    """Add Phase 5 fields to existing service-local PostgreSQL outbox tables.

    ``create_all`` creates new tables but does not evolve existing ones. These
    idempotent PostgreSQL statements keep a Phase 4 local database usable.
    Each caller invokes this only against its own service database.
    """
    statements = (
        """ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS status
        VARCHAR(16) NOT NULL DEFAULT 'PENDING'""",
        """ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS created_at
        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP""",
        """ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS updated_at
        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP""",
        "ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ NULL",
        "ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NULL",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


