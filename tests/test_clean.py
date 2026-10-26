import numpy as np
import pandas as pd
import pytest

from sca import clean as cl


def test_to_snake():
    assert cl.to_snake("Order Item Id") == "order_item_id"
    assert cl.to_snake("Late_delivery_risk") == "late_delivery_risk"
    assert cl.to_snake("Days for shipping (real)") == "days_for_shipping_real"


def test_standardize_columns_uses_explicit_renames(raw_sample):
    df = cl.standardize_columns(raw_sample)
    assert all(c == c.lower() and " " not in c for c in df.columns)
    assert {"shipping_days_real", "net_sales", "order_ts", "payment_type"} <= set(df.columns)


def test_pii_and_useless_columns_dropped_with_reasons(clean_log, flat):
    dropped = dict(clean_log.dropped_columns)
    for col in ("customer_email", "customer_password", "customer_fname", "customer_street"):
        assert col in dropped and col not in flat.columns
    assert "product_description" in dropped
    assert all(reason for reason in dropped.values())


def test_redundant_pair_dropped_only_when_identical(clean_log, flat):
    # Customer id pair is identical in the data, so the duplicate goes.
    assert "order_customer_id" in dict(clean_log.dropped_columns)
    # Sales vs Order Item Total differ (discounts), so both columns must survive.
    assert {"gross_sales", "net_sales"} <= set(flat.columns)
    assert any(a == "gross_sales" and m < 1 for a, _, m in clean_log.kept_pairs)


def test_redundancy_check_keeps_non_identical_pair():
    df = pd.DataFrame({"customer_id": [1, 2, 3], "order_customer_id": [1, 2, 99], "x": [1.0, 2.0, 3.0]})
    out = cl.drop_columns(df, cl.CleaningLog())
    assert "order_customer_id" in out.columns


def test_dates_parsed_with_explicit_format():
    df = pd.DataFrame({"order_ts": ["1/31/2018 22:56"], "ship_ts": ["2/3/2018 22:56"]})
    out = cl.parse_dates(df)
    assert out.loc[0, "order_ts"] == pd.Timestamp("2018-01-31 22:56")
    assert out.loc[0, "ship_ts"].month == 2
    with pytest.raises(ValueError):
        cl.parse_dates(pd.DataFrame({"order_ts": ["2018-31-01"], "ship_ts": ["2018-31-01"]}))


def test_derived_fields(flat):
    assert (flat["shipping_delay_days"] == flat["shipping_days_real"] - flat["shipping_days_scheduled"]).all()
    assert (flat["is_late"] == (flat["shipping_delay_days"] > 0).astype(int)).all()
    assert flat["order_week"].dt.day_of_week.eq(0).all()
    assert flat["order_month"].dt.day.eq(1).all()
    cancelled = flat["order_status"].isin(cl.EXCLUDED_STATUSES)
    assert (flat.loc[cancelled, "is_valid_order"] == 0).all()
    assert (flat.loc[~cancelled, "is_valid_order"] == 1).all()


def test_categoricals_standardised(flat):
    assert "EE. UU." not in set(flat["customer_country"])
    assert not flat["region"].str.contains(r"^\s|\s$|\s\s", regex=True).any()
    assert not flat["customer_state"].str.fullmatch(r"\d+").any()


def test_clean_keeps_every_row_and_logs_counts(raw_sample, clean_log, flat):
    assert clean_log.rows_raw == len(raw_sample)
    assert clean_log.rows_clean == len(flat) == len(raw_sample)


def test_star_schema_shapes(tables, flat):
    assert len(tables["fact_order_items"]) == len(flat)
    assert tables["dim_shipping_mode"]["shipping_mode"].is_unique
    assert (
        not tables["dim_customer"]
        .columns.intersection(["customer_fname", "customer_lname", "customer_email", "customer_street"])
        .size
    )
    d = tables["dim_date"]
    assert d["date"].is_monotonic_increasing and d["date"].diff().dropna().eq(pd.Timedelta("1D")).all()


def _weekly(counts: list[int]) -> pd.Series:
    weeks = pd.date_range("2016-01-04", periods=len(counts), freq="7D")
    return pd.Series(np.repeat(weeks, counts))


def test_tail_detected_and_cutoff_is_last_normal_day():
    weeks = _weekly([100] * 60 + [40] * 10 + [38])  # last element is a partial week
    res = cl.detect_tail_cutoff(weeks)
    assert res["abnormal_tail"]
    first_tail = pd.Timestamp("2016-01-04") + pd.Timedelta(weeks=60)
    assert res["first_abnormal_week"] == first_tail.date().isoformat()
    assert res["last_normal_date"] == (first_tail - pd.Timedelta(days=1)).date().isoformat()


def test_no_tail_when_volume_is_stable():
    rng = np.random.default_rng(0)
    res = cl.detect_tail_cutoff(_weekly(list(rng.integers(95, 105, size=70))))
    assert not res["abnormal_tail"]


def test_one_low_week_is_not_a_tail():
    res = cl.detect_tail_cutoff(_weekly([100] * 50 + [30] + [100] * 10))
    assert not res["abnormal_tail"]


def test_duplicate_category_names_are_disambiguated(raw_sample):
    raw = raw_sample.copy()
    # Same name, different id and department -> must become distinguishable.
    raw.loc[raw["Category Id"] == raw["Category Id"].iloc[0], "Category Name"] = "Twin"
    other = raw["Category Id"] != raw["Category Id"].iloc[0]
    raw.loc[other & (raw["Category Id"] == raw.loc[other, "Category Id"].iloc[0]), "Category Name"] = "Twin"
    flat, log = cl.clean_orders(raw)
    twins = flat[flat["category_name"].str.startswith("Twin")]
    assert twins["category_name"].nunique() == twins["category_id"].nunique() >= 2
    assert any("Twin" in note for note in log.value_fixes)
