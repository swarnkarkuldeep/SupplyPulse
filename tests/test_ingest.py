import json

import pandas as pd

from sca import ingest
from sca.config import SAMPLE_FILE, RunPaths, load_config

from .conftest import SAMPLE_PATH


def test_sample_keeps_whole_orders_and_has_no_personal_data(raw_sample):
    per_order_dates = raw_sample.groupby("Order Id")["order date (DateOrders)"].nunique()
    assert (per_order_dates == 1).all()
    for col in ingest.PII_RAW:
        assert set(raw_sample[col].unique()) == {ingest.MASKED}
    assert 2000 < len(raw_sample) < 3500


def test_sample_covers_every_market_and_shipping_mode(raw_sample):
    assert raw_sample["Market"].nunique() == 5
    assert raw_sample["Shipping Mode"].nunique() == 4


def test_make_sample_is_reproducible(raw_sample):
    a = ingest.make_sample(raw_sample, 500, ["Market", "Shipping Mode"], seed=1)
    b = ingest.make_sample(raw_sample, 500, ["Market", "Shipping Mode"], seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) < len(raw_sample)


def test_encoding_report_detects_latin1():
    rep = ingest.encoding_report(SAMPLE_PATH, "latin-1")
    assert rep["latin-1"] == "decodes cleanly"


def test_run_ingest_writes_tables_reports_and_meta(tmp_path):
    cfg = load_config()
    paths = RunPaths(SAMPLE_PATH.parent / SAMPLE_FILE, tmp_path / "proc", tmp_path / "rep")
    meta = ingest.run_ingest(cfg, paths, sample=True)
    assert meta["rows_raw"] == meta["rows_clean"]
    for table in ingest.TABLE_ORDER:
        assert (paths.processed_dir / f"{table}.parquet").exists()
    for report in ("data_profile.md", "cleaning_log.md"):
        assert (paths.reports_dir / report).exists()
    assert (paths.figures_dir / "profile_monthly_orders.png").exists()
    saved = json.loads((paths.processed_dir / ingest.META_FILE).read_text())
    assert saved["rows_clean"] == meta["rows_clean"]
    assert set(ingest.read_processed(paths.processed_dir)) == set(ingest.TABLE_ORDER)
