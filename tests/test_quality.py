import json

import pandas as pd
import pytest

from sca import quality as q


def _results(tables, tail=None):
    return {r.name: r for r in q.run_checks(tables, tail)}


def test_clean_sample_has_no_error_failures(tables):
    res = q.run_checks(tables)
    assert q.failures(res, q.ERROR) == []
    q.enforce(res)  # does not raise


def test_every_check_has_name_description_severity(tables):
    for r in q.run_checks(tables):
        assert r.name and r.description and r.severity in (q.ERROR, q.WARN)


def _dup_pk(t):
    f = t["fact_order_items"]
    f.loc[1, "order_item_id"] = f.loc[0, "order_item_id"]


def _null_critical(t):
    t["fact_order_items"].loc[0, "net_sales"] = None


def _orphan_fk(t):
    t["fact_order_items"].loc[0, "customer_key"] = 10**9


def _orphan_date(t):
    t["fact_order_items"].loc[0, "ship_date_key"] = 19000101


def _zero_qty(t):
    t["fact_order_items"].loc[0, "quantity"] = 0


def _bad_rate(t):
    t["fact_order_items"].loc[0, "discount_rate"] = 1.5


def _neg_price(t):
    t["fact_order_items"].loc[0, "unit_price"] = -1.0


def _ship_before_order(t):
    f = t["fact_order_items"]
    f.loc[0, "ship_ts"] = f.loc[0, "order_ts"] - pd.Timedelta(days=2)


def _break_gross(t):
    t["fact_order_items"].loc[0, "gross_sales"] += 50


def _break_net(t):
    t["fact_order_items"].loc[0, "net_sales"] += 50


def _flip_label(t):
    f = t["fact_order_items"]
    i = f.index[f["is_valid_order"] == 1][0]
    f.loc[i, "late_delivery_risk"] = 1 - f.loc[i, "late_delivery_risk"]


def _duplicate_item(t):
    f = t["fact_order_items"]
    dup = f.iloc[[0]].copy()
    dup["order_item_id"] = f["order_item_id"].max() + 1
    t["fact_order_items"] = pd.concat([f, dup], ignore_index=True)


def _order_inconsistent(t):
    f = t["fact_order_items"]
    multi = f.groupby("order_id").filter(lambda g: len(g) > 1)
    i = multi.index[0]
    f.loc[i, "shipping_mode_key"] = (f.loc[i, "shipping_mode_key"] % 4) + 1


def _dup_dim_pk(t):
    d = t["dim_customer"]
    d.loc[1, "customer_key"] = d.loc[0, "customer_key"]


def _dup_category_name(t):
    d = t["dim_category"]
    d.loc[1, "category_name"] = d.loc[0, "category_name"]


def _dup_natural_key(t):
    d = t["dim_product"]
    d.loc[1, "product_card_id"] = d.loc[0, "product_card_id"]


BROKEN = [
    (_dup_pk, "pk_unique__fact_order_items"),
    (_dup_dim_pk, "pk_unique__dim_customer"),
    (_dup_natural_key, "natural_key_unique__dim_product"),
    (_dup_category_name, "label_unique__dim_category.category_name"),
    (_null_critical, "not_null__fact_order_items"),
    (_orphan_fk, "fk__fact_order_items.customer_key->dim_customer"),
    (_orphan_date, "fk__fact_order_items.ship_date_key->dim_date"),
    (_zero_qty, "quantity_positive"),
    (_bad_rate, "discount_rate_in_0_1"),
    (_neg_price, "prices_non_negative"),
    (_ship_before_order, "ship_not_before_order"),
    (_break_gross, "recon_gross_sales"),
    (_break_net, "recon_net_sales"),
    (_flip_label, "label_consistency_valid_orders"),
    (_duplicate_item, "no_duplicate_order_items"),
    (_order_inconsistent, "order_level_consistency"),
]


@pytest.mark.parametrize(("mutate", "check"), BROKEN, ids=[b[1] for b in BROKEN])
def test_check_catches_broken_fixture(tables, mutate, check):
    mutate(tables)
    res = _results(tables)
    assert not res[check].passed, f"{check} did not catch the problem"
    assert res[check].failing_rows >= 1 and res[check].sample_keys
    assert res[check].severity == q.ERROR
    with pytest.raises(q.QualityGateError):
        q.enforce(list(res.values()))


def test_warn_severity_check_does_not_block(tables):
    d = tables["dim_product"]
    d.loc[0, "product_name"] = "Caf�"
    res = _results(tables)
    assert not res["no_mojibake__dim_product"].passed
    q.enforce(list(res.values()))  # warn only: no raise


def test_tail_warning_reported(tables):
    tail = {"abnormal_tail": True, "first_abnormal_week": "2017-10-02", "tail_weeks": 17}
    assert not _results(tables, tail)["volume_tail_abnormal"].passed


def test_reports_written_in_markdown_and_json(tables, tmp_path):
    q.write_reports(q.run_checks(tables), tmp_path)
    payload = json.loads((tmp_path / "data_quality_report.json").read_text())
    assert payload["n_checks"] == len(payload["checks"]) > 20
    assert payload["failing_errors"] == 0
    md = (tmp_path / "data_quality_report.md").read_text()
    assert "Failing error checks" in md and "pk_unique__fact_order_items" in md
