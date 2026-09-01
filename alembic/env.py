import re
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Runtime-created location_pings partitions (premake job / migration 0014)
# are not declarative metadata; without this filter autogenerate would
# propose dropping every partition.
RUNTIME_PARTITION_NAME = re.compile(r"^location_pings_p\d{4}_\d{2}$|^location_pings_legacy$")
EXTENSION_OWNED_TABLES = frozenset({"spatial_ref_sys"})


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ARG001
    if type_ == "table" and reflected and name is not None:
        if name in EXTENSION_OWNED_TABLES or RUNTIME_PARTITION_NAME.match(name):
            return False
    return True


def compare_server_default(
    context,  # noqa: ARG001
    inspected_column,
    metadata_column,  # noqa: ARG001
    inspected_default,
    metadata_default,  # noqa: ARG001
    rendered_metadata_default,
):
    inspected_type = inspected_column.type
    if isinstance(inspected_type, postgresql.JSON) and not isinstance(
        inspected_type, postgresql.JSONB
    ):
        return inspected_default != rendered_metadata_default
    return None


def get_database_url() -> str:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL must be configured to run Alembic migrations")
    return settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=compare_server_default,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        compare_server_default=compare_server_default,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
