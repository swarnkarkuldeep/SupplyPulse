import pandas as pd
import pytest
from sqlalchemy import text

from sca.config import Env
from sca.db import build_url, dialect_dir, get_engine


def test_sqlite_roundtrip(tmp_path):
    env = Env(_env_file=None, db_backend="sqlite", sqlite_path=str(tmp_path / "t.db"))
    engine = get_engine(env)
    pd.DataFrame({"a": [1, 2, 3]}).to_sql("t", engine, index=False)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM t")).scalar() == 3
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
    assert dialect_dir(engine) == "sqlite"


def test_sqlserver_url_local_docker():
    env = Env(_env_file=None, db_backend="sqlserver", db_password="p@ss/word")
    url = build_url(env)
    assert url.drivername == "mssql+pyodbc"
    assert url.host == "localhost" and url.port == 1433
    assert url.query["driver"] == "ODBC Driver 18 for SQL Server"
    assert url.query["TrustServerCertificate"] == "yes"
    assert url.password == "p@ss/word"


def test_azure_url_verifies_certificate():
    env = Env(_env_file=None, db_backend="azure", db_host="x.database.windows.net")
    url = build_url(env)
    assert url.query["Encrypt"] == "yes"
    assert url.query["TrustServerCertificate"] == "no"


def test_database_url_overrides_backend():
    env = Env(_env_file=None, db_backend="sqlserver", database_url="sqlite:///:memory:")
    assert build_url(env).get_backend_name() == "sqlite"


def test_invalid_backend_rejected():
    with pytest.raises(ValueError):
        Env(_env_file=None, db_backend="oracle")
