"""Alembic environment. The database URL comes from app settings (DATABASE_URL / backend/.env).

Migration 0001 applies the validated schema_v2.sql verbatim (it has CHECK constraints, triggers, views and a plpgsql
function that SQLAlchemy metadata cannot express). The ORM models in app/models map onto those tables; they are NOT used
for autogenerate.
"""
from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings

config = context.config
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
