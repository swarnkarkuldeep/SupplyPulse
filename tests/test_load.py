import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from sca import load
from sca.config import Env
from sca.db import get_engine


@pytest.fixture
def engine(tmp_path):
    return get_engine(Env(_env_file=None, db_backend="sqlite", sqlite_path=str(tmp_path / "t.db")))


def _count(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


def test_round_trip_row_counts_match(engine, tables):
    counts = load.load_tables(engine, tables)
    assert counts == {name: len(tables[name]) for name in load.LOAD_ORDER}


def test_load_is_idempotent(engine, tables):
    load.load_tables(engine, tables)
    load.load_tables(engine, tables)
    assert _count(engine, "SELECT COUNT(*) FROM fact_order_items") == len(tables["fact_order_items"])


def test_foreign_keys_enforced(engine, tables):
    load.load_tables(engine, tables)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE fact_order_items SET customer_key = -1 WHERE order_item_id = (SELECT MIN(order_item_id) FROM fact_order_items)"
            )
        )


def test_views_exist_and_reconcile_with_fact(engine, tables):
    load.load_tables(engine, tables)
    valid_net = _count(engine, "SELECT SUM(net_sales) FROM fact_order_items WHERE is_valid_order = 1")
    valid_units = _count(engine, "SELECT SUM(quantity) FROM fact_order_items WHERE is_valid_order = 1")
    assert _count(engine, "SELECT SUM(revenue) FROM vw_kpi_monthly") == pytest.approx(valid_net)
    assert _count(engine, "SELECT SUM(units) FROM vw_weekly_demand") == valid_units
    assert _count(engine, "SELECT SUM(sales) FROM vw_margin_analysis") == pytest.approx(valid_net)
    valid_orders = _count(engine, "SELECT COUNT(DISTINCT order_id) FROM fact_order_items WHERE is_valid_order = 1")
    assert _count(engine, "SELECT SUM(orders) FROM vw_delivery_performance") == valid_orders
    assert _count(engine, "SELECT SUM(orders) FROM vw_kpi_monthly") == valid_orders


def test_kpi_view_month_on_month_uses_lag(engine, tables):
    load.load_tables(engine, tables)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT order_month, revenue, revenue_mom_pct FROM vw_kpi_monthly ORDER BY order_month")
        ).all()
    assert rows[0][2] is None
    expected = round(100 * (rows[1][1] - rows[0][1]) / rows[0][1], 2)
    assert rows[1][2] == pytest.approx(expected, abs=0.01)


def test_split_statements_ignores_comments_and_blanks():
    sql = "-- header\nCREATE TABLE a (x INT);\n\n-- only comment;\nCREATE TABLE b (y INT);\n"
    stmts = load.split_statements(sql)
    assert len(stmts) == 2 and "TABLE a" in stmts[0] and "TABLE b" in stmts[1]
