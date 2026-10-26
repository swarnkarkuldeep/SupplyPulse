import re
from pathlib import Path

import pytest

from sca import results

ROOT = Path(__file__).resolve().parents[1]

V = {
    "rows_raw": 180519, "rows_clean": 180519, "cutoff": "2017-10-01", "tail_drop_pct": 0.6,
    "dq_checks": 47, "dq_error_checks": 38, "dq_warn_checks": 9, "dq_failing_errors": 0, "dq_failing_warnings": 2,
    "n_categories": 9, "categories": ["A"], "sparse_zero_share": 0.16, "folds": 5, "horizon_weeks": 8,
    "forecast_champion": "sarima", "wape": 0.081, "mape": 0.085, "wape_naive": 0.106, "wape_ma": 0.083,
    "wape_improvement": 0.234, "wape_total": 0.037, "forecast_models": {},
    "risk_champion": "lightgbm", "roc_auc": 0.778, "pr_auc": 0.859, "roc_auc_mode_only": 0.744,
    "precision": 0.897, "recall": 0.589, "risk_base_rate": 0.574,
    "stockout_before": 0.99, "stockout_after": 0.39, "holding_before": 36011.0, "holding_after": 48792.0,
    "textbook_service_95": 0.829, "dax_measures": 55, "tests": 200, "revenue": 31644664.75, "profit": 3806420.63,
    "margin": 0.1203, "orders": 62897, "on_time": 0.4269, "loss_items_share": 0.187, "loss_vs_gross_profit": 0.49,
    "loss_top10_products": 0.9, "discount_coef": -0.01, "discount_p": 0.54, "discount_r2": 0.0003,
    "late_first_class": 1.0, "late_standard": 0.398, "excluded_share": 0.043, "n_review_packs": 2,
}  # fmt: skip


def test_readme_template_resolves_every_placeholder():
    text = results.render_readme(V)
    assert "{{" not in text and "}}" not in text
    for expected in ("8.1%", "0.778", "0.744", "83%", "47", "sarima".upper()):
        assert expected in text


def test_unknown_placeholder_in_the_template_is_an_error(tmp_path, monkeypatch):
    t = tmp_path / "t.md"
    t.write_text("value {{not_a_key}}", encoding="utf-8")
    monkeypatch.setattr(results, "TEMPLATE", t)
    with pytest.raises(KeyError, match="not_a_key"):
        results.render_readme(V)


def test_results_table_has_the_required_rows_and_sources():
    md = results.results_markdown(V)
    for metric in (
        "Raw rows", "Clean rows", "Data-quality checks", "Categories forecast", "Champion forecast model",
        "Forecast WAPE", "Forecast MAPE", "Improvement over seasonal naive", "Late-risk ROC-AUC", "Late-risk PR-AUC",
        "Simulated stockout risk", "Holding cost change", "DAX measures", "Tests",
    ):  # fmt: skip
        assert metric in md, metric
    rows = [r for r in md.splitlines() if r.startswith("| ") and "---" not in r and "Metric" not in r]
    assert all(r.count("|") == 5 and r.rstrip().endswith("` |") for r in rows)  # metric | value | how | source
    assert "WAPE" in md.split("## Which forecast metric to quote")[1]
    assert "illustrative" not in md.lower().replace("nothing is illustrative", "")


def test_dax_measure_counter_matches_the_file():
    n = results.count_dax_measures(ROOT / "dashboard" / "dax_measures.md")
    assert n >= 40


@pytest.mark.skipif(
    not (ROOT / "reports" / "RESULTS.md").exists() or not (ROOT / "README.md").exists(), reason="results not built"
)
def test_committed_readme_quotes_the_same_numbers_as_results():
    results_md = (ROOT / "reports" / "RESULTS.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for label in ("Forecast WAPE", "Late-risk ROC-AUC (test)", "Shipping-mode-only ROC-AUC"):
        value = re.search(rf"\| {re.escape(label)} \| ([^|]+) \|", results_md).group(1).strip()
        assert value in readme, f"{label} = {value} not found in the README"
    assert "{{" not in readme
