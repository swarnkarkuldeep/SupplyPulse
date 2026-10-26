"""Load the star schema and SQL views into the database (truncate-and-load, idempotent)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

from sca.config import PROJECT_ROOT
from sca.db import dialect_dir

log = logging.getLogger(__name__)

# Parents first. Deletes run in reverse so foreign keys are never violated.
LOAD_ORDER = [
    "dim_category", "dim_product", "dim_customer", "dim_geography",
    "dim_shipping_mode", "dim_date", "fact_order_items",
]  # fmt: skip
DATE_COLUMNS = {
    "dim_date": ["date", "week_start"],
    "fact_order_items": ["order_week", "order_month"],
}
CHUNK_ROWS = 20_000


class LoadError(RuntimeError):
    """Raised when the loaded row counts do not match the cleaned data."""


def split_statements(sql: str) -> list[str]:
    """Split a script on semicolons that end a line; drop empty chunks."""
    parts = re.split(r";[ \t]*(?:\r?\n|$)", sql)
    return [p.strip() for p in parts if re.sub(r"--[^\n]*", "", p).strip()]


def sql_dir(engine: Engine, root: Path | None = None) -> Path:
    """Folder with this dialect's schema.sql (views are shared, see view_statements)."""
    return (root or PROJECT_ROOT / "sql") / dialect_dir(engine)


def create_schema(engine: Engine, root: Path | None = None) -> None:
    """Create tables and indexes if they do not exist."""
    script = (sql_dir(engine, root) / "schema.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        for stmt in split_statements(script):
            conn.exec_driver_sql(stmt)


def view_files(root: Path | None = None) -> list[Path]:
    """View definitions, written once in T-SQL-compatible SQL that SQLite also accepts."""
    return sorted(((root or PROJECT_ROOT / "sql") / "sqlserver" / "views").glob("*.sql"))


def create_views(engine: Engine, root: Path | None = None) -> list[str]:
    """(Re)create every view. SQLite lacks CREATE OR ALTER, so it drops then creates."""
    names = []
    with engine.begin() as conn:
        for path in view_files(root):
            sql = path.read_text(encoding="utf-8")
            name = re.search(r"VIEW\s+(\w+)", sql).group(1)
            if engine.dialect.name == "sqlite":
                conn.exec_driver_sql(f"DROP VIEW IF EXISTS {name}")
                sql = sql.replace("CREATE OR ALTER VIEW", "CREATE VIEW")
            conn.exec_driver_sql(sql.strip().rstrip(";"))
            names.append(name)
    return names


def prepare_for_sql(table: str, df: pd.DataFrame) -> pd.DataFrame:
    """Convert pure-date columns to python dates so DATE columns hold no time part."""
    out = df.copy()
    for col in DATE_COLUMNS.get(table, []):
        out[col] = out[col].dt.date
    return out


def truncate_all(engine: Engine) -> None:
    """Delete every row, children before parents."""
    with engine.begin() as conn:
        for table in reversed(LOAD_ORDER):
            conn.execute(text(f"DELETE FROM {table}"))


def load_tables(engine: Engine, tables: dict[str, pd.DataFrame], root: Path | None = None) -> dict[str, int]:
    """Create the schema if needed, truncate, load all tables, verify counts, build views."""
    create_schema(engine, root)
    truncate_all(engine)
    for name in LOAD_ORDER:
        prepare_for_sql(name, tables[name]).to_sql(name, engine, if_exists="append", index=False, chunksize=CHUNK_ROWS)
        log.info("loaded %s (%s rows)", name, f"{len(tables[name]):,}")
    counts = {}
    with engine.connect() as conn:
        for name in LOAD_ORDER:
            counts[name] = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one()
    mismatched = {n: (c, len(tables[n])) for n, c in counts.items() if c != len(tables[n])}
    if mismatched:
        raise LoadError(f"row count mismatch (loaded, expected): {mismatched}")
    create_views(engine, root)
    return counts


# Phase outputs saved as parquet under data/processed, loaded as extra tables when present.
EXTRA_TABLES = {
    "fct_forecast": "forecast/fct_forecast.parquet",
    "fct_late_risk_scores": "risk/fct_late_risk_scores.parquet",
    "fct_shap_drivers": "risk/fct_shap_drivers.parquet",
}


def load_extra_tables(engine: Engine, processed_dir: Path) -> list[str]:
    """Load model-output tables (e.g. fct_forecast) that earlier stages wrote, if they exist."""
    loaded = []
    for table, rel in EXTRA_TABLES.items():
        path = processed_dir / rel
        if path.exists():
            pd.read_parquet(path).to_sql(table, engine, if_exists="replace", index=False, chunksize=CHUNK_ROWS)
            loaded.append(table)
    return loaded
