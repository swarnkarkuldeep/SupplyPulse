"""SQLAlchemy engine factory: SQL Server (Docker), Azure SQL, or SQLite from .env."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url

from sca.config import PROJECT_ROOT, Env, get_env


def build_url(env: Env) -> URL:
    """Build the SQLAlchemy URL for the configured backend (no connection is made)."""
    if env.database_url:
        return make_url(env.database_url)
    if env.db_backend == "sqlite":
        path = Path(env.sqlite_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return URL.create("sqlite", database=str(path))
    # Azure SQL needs a verified cert; local Docker uses a self-signed one.
    trust = "no" if env.db_backend == "azure" else env.trust_server_certificate
    return URL.create(
        "mssql+pyodbc",
        username=env.db_user,
        password=env.db_password,
        host=env.db_host,
        port=env.db_port,
        database=env.db_name,
        query={
            "driver": env.odbc_driver,
            "Encrypt": "yes",
            "TrustServerCertificate": trust,
        },
    )


def get_engine(env: Env | None = None) -> Engine:
    """Create an engine for the configured backend.

    The same code path serves SQL Server, Azure SQL and SQLite; only .env changes.
    """
    env = env or get_env()
    url = build_url(env)
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url)

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_conn, _record):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(url, fast_executemany=True)


def ensure_database(env: Env) -> None:
    """Create the target database on a local SQL Server if it is missing.

    Azure SQL databases are provisioned in the portal, so this only acts on backend 'sqlserver'.
    """
    if env.db_backend != "sqlserver" or env.database_url:
        return
    master = create_engine(
        build_url(env.model_copy(update={"db_name": "master"})), isolation_level="AUTOCOMMIT"
    )
    with master.connect() as conn:
        conn.exec_driver_sql(f"IF DB_ID(N'{env.db_name}') IS NULL CREATE DATABASE [{env.db_name}]")
    master.dispose()


def dialect_dir(engine: Engine) -> str:
    """Name of the sql/ subfolder holding dialect-specific files for this engine."""
    return "sqlite" if engine.dialect.name == "sqlite" else "sqlserver"
