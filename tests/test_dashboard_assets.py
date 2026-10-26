import json
import re
from pathlib import Path

import pandas as pd
import pytest

from sca import kpis, load
from sca.config import load_config

DASH = Path(__file__).resolve().parents[1] / "dashboard"
DAX = (DASH / "dax_measures.md").read_text(encoding="utf-8")
BLOCKS = re.findall(r"### (.+?)\n```dax\n(.*?)```", DAX, flags=re.S)
SPEC = (DASH / "dashboard_spec.md").read_text(encoding="utf-8")

REQUIRED_MEASURES = [
    "Total Revenue", "Total Profit", "Margin %", "Orders", "Average Order Value", "On-Time Delivery %",
    "Late Orders", "Average Delay Days", "Forecast WAPE", "Revenue MoM %", "Revenue YoY %",
]  # fmt: skip


def schema(tables) -> dict[str, set[str]]:
    out = {name: set(df.columns) for name, df in tables.items() if name in kpis.STAR_TABLES}
    out.update({name: set(cols) for name, cols in kpis.MODEL_TABLE_COLUMNS.items()})
    return out


def test_every_measure_block_is_a_definition_of_its_own_name():
    assert len(BLOCKS) >= 40
    names = [n for n, _ in BLOCKS]
    assert len(names) == len(set(names)), "duplicate measure names"
    for name, code in BLOCKS:
        assert re.match(rf"{re.escape(name)}\s*=", code.strip()), f"{name}: code must start with '{name} ='"


def test_required_spec_measures_exist():
    names = {n for n, _ in BLOCKS}
    assert set(REQUIRED_MEASURES) <= names


def test_every_column_reference_exists_in_the_model(tables):
    sch = schema(tables)
    bad = []
    for name, code in BLOCKS:
        for table, col in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]", code):
            if table not in sch or col not in sch[table]:
                bad.append(f"{name}: {table}[{col}]")
    assert not bad, bad


def test_every_measure_reference_is_defined():
    names = {n for n, _ in BLOCKS}
    bad = []
    for name, code in BLOCKS:
        body = re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\[[^\]]+\]", "", code)  # drop table[column]
        body = re.sub(r'"[^"]*"', "", body)  # drop string literals (format strings)
        for ref in re.findall(r"\[([^\]]+)\]", body):
            if ref not in names:
                bad.append(f"{name}: [{ref}]")
    assert not bad, bad


def test_dax_brackets_and_parentheses_balance():
    for name, code in BLOCKS:
        stripped = re.sub(r'"[^"]*"', "", code)
        assert stripped.count("(") == stripped.count(")"), name
        assert stripped.count("[") == stripped.count("]"), name
        assert stripped.count("{") == stripped.count("}"), name


def test_business_measures_exclude_invalid_orders():
    """Measures on the order fact must carry the valid-order filter (or be built from one that does)."""
    base = {"Total Revenue", "Gross Sales", "Discount Amount", "Total Profit", "Units Sold", "Orders", "Late Orders"}
    for name, code in BLOCKS:
        if name in base:
            assert "is_valid_order] = 1" in code, name


def test_every_measure_used_in_the_spec_exists():
    names = {n for n, _ in BLOCKS}
    used = set(re.findall(r"`\[([^\]]+)\]`", SPEC))
    assert used <= names, used - names


def test_every_spec_field_reference_exists(tables):
    sch = schema(tables)
    bad = []
    for table, col in re.findall(r"`([a-z_]+)\[([a-z_]+)\]`", SPEC):
        if table not in sch or col not in sch[table]:
            bad.append(f"{table}[{col}]")
    assert not bad, bad


def test_spec_covers_the_four_pages_and_titles_state_insights():
    for page in ("Page 1", "Page 2", "Page 3", "Page 4"):
        assert page in SPEC
    assert SPEC.count("`[Title ") >= 8


def test_theme_is_valid_and_colour_blind_safe_palette():
    theme = json.loads((DASH / "theme.json").read_text(encoding="utf-8"))
    assert theme["name"] and len(theme["dataColors"]) >= 8
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in theme["dataColors"])
    from sca.viz import PALETTE

    assert {c.upper() for c in list(PALETTE.values())[:7]} <= {c.upper() for c in theme["dataColors"]}


def test_build_guide_lists_every_table_and_relationship():
    guide = (DASH / "BUILD_GUIDE.md").read_text(encoding="utf-8")
    for t in [*kpis.STAR_TABLES, *kpis.MODEL_TABLE_COLUMNS]:
        assert t in guide, t
    assert "Mark as date table" in guide and "localhost,1433" in guide


# ---------------------------------------------------------------- numbers behind the assets


def test_kpi_monthly_matches_the_sql_view(tables, tmp_path):
    """pandas KPIs and vw_kpi_monthly must agree, so the dashboard and the pipeline tell one story."""
    from sca.config import Env
    from sca.db import get_engine

    engine = get_engine(Env(_env_file=None, db_backend="sqlite", sqlite_path=str(tmp_path / "k.db")))
    load.load_tables(engine, tables)
    sql = pd.read_sql("SELECT * FROM vw_kpi_monthly ORDER BY order_month", engine)
    py = kpis.kpi_monthly(tables)
    assert len(sql) == len(py)
    for col in ("orders", "revenue", "profit", "margin_pct", "on_time_pct", "avg_order_value"):
        assert sql[col].astype(float).to_numpy() == pytest.approx(py[col].astype(float).to_numpy(), abs=0.011)


def test_reconciliation_numbers_are_consistent(tables):
    r = kpis.reconciliation(tables)
    assert r["Margin %"] == pytest.approx(r["Total Profit"] / r["Total Revenue"])
    assert r["On-Time Delivery %"] == pytest.approx(1 - r["Late Orders"] / r["Orders"])
    md = kpis.reconciliation_markdown(tables)
    assert "`[Total Revenue]`" in md and "no slicers" in md


def test_export_writes_every_table_and_a_manifest(tables, tmp_path):
    counts = kpis.export_dashboard_data(tables, tmp_path / "missing_models", tmp_path / "out")
    assert set(counts) == set(kpis.STAR_TABLES)  # model tables are skipped when their outputs do not exist
    assert (tmp_path / "out" / "fact_order_items.parquet").exists()
    assert (tmp_path / "out" / "fact_order_items.csv").exists()
    assert json.loads((tmp_path / "out" / "manifest.json").read_text())["fact_order_items"] == len(
        tables["fact_order_items"]
    )


def test_scorecard_page_draws_from_the_sample(tables, tmp_path):
    path = kpis.page_scorecard(tables, tmp_path, tail={"abnormal_tail": True, "first_abnormal_week": "2017-10-02"})
    assert path.exists() and path.stat().st_size > 10_000
    assert kpis.page_margin(tables, tmp_path).exists()


def test_forecast_page_and_risk_page_are_skipped_without_inputs(tmp_path):
    assert kpis.page_forecast(tmp_path, tmp_path) is None
    assert kpis.page_risk(tmp_path, tmp_path) is None


def test_config_loads_for_all_stages():
    assert load_config().simulation.n_sims == 10_000
