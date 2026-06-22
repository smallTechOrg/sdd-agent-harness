import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

# Add src/ to sys.path so that `analyst` package can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from analyst.config.settings import get_settings  # noqa: E402
from analyst.db.models import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_sync_url() -> str:
    """Return a synchronous SQLite URL, stripping +aiosqlite if present."""
    url = os.environ.get("ANALYST_DATABASE_URL") or get_settings().database_url
    return (
        url.replace("sqlite+aiosqlite://", "sqlite:///")
        .replace("sqlite+aiosqlite:/", "sqlite://")
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a synchronous engine."""
    url = _get_sync_url()
    connectable = create_engine(url, connect_args={"check_same_thread": False})

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
