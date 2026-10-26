"""Data-quality checks as code. Any failing `error` check stops the pipeline."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ERROR, WARN = "error", "warn"
SAMPLE_KEYS = 5
MONEY_TOL = 0.02

PRIMARY_KEYS = {
    "dim_category": "category_key",
    "dim_product": "product_key",
    "dim_customer": "customer_key",
    "dim_geography": "geography_key",
    "dim_shipping_mode": "shipping_mode_key",
    "dim_date": "date_key",
    "fact_order_items": "order_item_id",
}
NATURAL_KEYS = {
    "dim_category": ["category_id"],
    "dim_product": ["product_card_id"],
    "dim_customer": ["customer_id"],
    "dim_geography": ["market", "region", "country"],
    "dim_shipping_mode": ["shipping_mode"],
}
CRITICAL_COLUMNS = {
    "dim_category": ["category_key", "category_id", "category_name", "department_name"],
    "dim_product": ["product_key", "product_card_id", "product_name", "category_key"],
    "dim_customer": ["customer_key", "customer_id", "segment"],
    "dim_geography": ["geography_key", "market", "region", "country"],
    "dim_shipping_mode": ["shipping_mode_key", "shipping_mode", "scheduled_days"],
    "dim_date": ["date_key", "date"],
    "fact_order_items": [
        "order_item_id", "order_id", "order_ts", "ship_ts", "order_date_key", "ship_date_key",
        "customer_key", "product_key", "category_key", "geography_key", "shipping_mode_key",
        "quantity", "unit_price", "discount_rate", "gross_sales", "net_sales", "profit",
        "shipping_days_real", "shipping_days_scheduled", "late_delivery_risk", "is_valid_order",
    ],
}  # fmt: skip
FOREIGN_KEYS = [
    ("fact_order_items", "customer_key", "dim_customer"),
    ("fact_order_items", "product_key", "dim_product"),
    ("fact_order_items", "category_key", "dim_category"),
    ("fact_order_items", "geography_key", "dim_geography"),
    ("fact_order_items", "shipping_mode_key", "dim_shipping_mode"),
    ("fact_order_items", "order_date_key", "dim_date"),
    ("fact_order_items", "ship_date_key", "dim_date"),
    ("dim_product", "category_key", "dim_category"),
]
ORDER_LEVEL_COLUMNS = [
    "order_ts", "ship_ts", "customer_key", "geography_key", "shipping_mode_key",
    "order_status", "late_delivery_risk",
]  # fmt: skip


class QualityGateError(RuntimeError):
    """Raised when one or more error-severity checks fail."""


@dataclass
class CheckResult:
    """Outcome of one check."""

    name: str
    description: str
    severity: str
    table: str
    total_rows: int
    failing_rows: int
    sample_keys: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.failing_rows == 0


def _check(
    name: str,
    description: str,
    severity: str,
    table: str,
    df: pd.DataFrame,
    bad: pd.Series,
    key: str | None = None,
) -> CheckResult:
    """Build a CheckResult from a boolean 'row is bad' mask."""
    bad = bad.fillna(True).astype(bool)
    keys = df.loc[bad, key].head(SAMPLE_KEYS).tolist() if key and bad.any() else []
    return CheckResult(name, description, severity, table, len(df), int(bad.sum()), [_plain(k) for k in keys])


def _plain(v):
    return v.item() if isinstance(v, np.generic) else (str(v) if hasattr(v, "isoformat") else v)


def _ck_primary_keys(t: dict[str, pd.DataFrame]) -> list[CheckResult]:
    out = []
    for table, key in PRIMARY_KEYS.items():
        df = t[table]
        out.append(
            _check(
                f"pk_unique__{table}",
                f"`{key}` is unique and not null in {table}",
                ERROR,
                table,
                df,
                df[key].duplicated(keep=False) | df[key].isna(),
                key,
            )
        )
    for table, cols in NATURAL_KEYS.items():
        df = t[table]
        out.append(
            _check(
                f"natural_key_unique__{table}",
                f"Natural key ({', '.join(cols)}) is unique in {table}",
                ERROR,
                table,
                df,
                df.duplicated(subset=cols, keep=False),
                PRIMARY_KEYS[table],
            )
        )
    return out


UNIQUE_LABELS = {"dim_category": "category_name", "dim_product": "product_name"}


def _ck_labels(t: dict[str, pd.DataFrame]) -> list[CheckResult]:
    out = []
    for table, col in UNIQUE_LABELS.items():
        df = t[table]
        out.append(
            _check(
                f"label_unique__{table}.{col}",
                f"`{col}` identifies exactly one row of {table} (needed to forecast by name)",
                ERROR,
                table,
                df,
                df[col].duplicated(keep=False),
                PRIMARY_KEYS[table],
            )
        )
    return out


def _ck_not_null(t: dict[str, pd.DataFrame]) -> list[CheckResult]:
    out = []
    for table, cols in CRITICAL_COLUMNS.items():
        df = t[table]
        bad = df[cols].isna().any(axis=1)
        out.append(
            _check(
                f"not_null__{table}",
                f"No nulls in critical columns of {table}: {', '.join(cols)}",
                ERROR,
                table,
                df,
                bad,
                PRIMARY_KEYS[table],
            )
        )
    return out


def _ck_foreign_keys(t: dict[str, pd.DataFrame]) -> list[CheckResult]:
    out = []
    for child, col, parent in FOREIGN_KEYS:
        df = t[child]
        bad = ~df[col].isin(t[parent][PRIMARY_KEYS[parent]]) | df[col].isna()
        out.append(
            _check(
                f"fk__{child}.{col}->{parent}",
                f"Every {child}.{col} exists in {parent}",
                ERROR,
                child,
                df,
                bad,
                PRIMARY_KEYS[child],
            )
        )
    return out


def _ck_fact(t: dict[str, pd.DataFrame]) -> list[CheckResult]:
    f = t["fact_order_items"]
    k = "order_item_id"
    valid = f["is_valid_order"] == 1
    gross_gap = (f["gross_sales"] - f["unit_price"] * f["quantity"]).abs()
    net_gap = (f["net_sales"] - (f["gross_sales"] - f["discount_amount"])).abs()
    disc_gap = (f["discount_amount"] - f["discount_rate"] * f["gross_sales"]).abs()
    late_from_days = (f["shipping_days_real"] > f["shipping_days_scheduled"]).astype(int)
    pr_gap = (f["profit_ratio"] - f["profit"] / f["net_sales"]).abs()
    day_gap = (
        (f["ship_ts"].dt.normalize() - f["order_ts"].dt.normalize()).dt.days - f["shipping_days_real"]
    ).abs()
    dup_cols = [c for c in f.columns if c != "order_item_id"]
    grouped = f.groupby("order_id")[ORDER_LEVEL_COLUMNS].transform("nunique")
    checks = [
        ("quantity_positive", "quantity > 0", ERROR, f["quantity"] <= 0),
        ("discount_rate_in_0_1", "0 <= discount_rate <= 1", ERROR,
         (f["discount_rate"] < 0) | (f["discount_rate"] > 1)),
        ("prices_non_negative", "unit_price, gross_sales, net_sales and discount_amount are >= 0",
         ERROR, (f[["unit_price", "gross_sales", "net_sales", "discount_amount"]] < 0).any(axis=1)),
        ("ship_not_before_order", "ship_ts >= order_ts", ERROR, f["ship_ts"] < f["order_ts"]),
        ("recon_gross_sales",
         f"gross_sales = unit_price x quantity (tolerance {MONEY_TOL})", ERROR,
         gross_gap > MONEY_TOL),
        ("recon_net_sales",
         f"net_sales = gross_sales - discount_amount (tolerance {MONEY_TOL})", ERROR,
         net_gap > MONEY_TOL),
        ("recon_discount_rate",
         "discount_amount = discount_rate x gross_sales (rate is rounded to 2 decimals)", WARN,
         disc_gap > 0.005 * f["gross_sales"] + MONEY_TOL),
        ("recon_profit_ratio", "profit_ratio = profit / net_sales (within 0.01)", WARN,
         pr_gap > 0.01),
        ("shipping_days_match_dates",
         "shipping_days_real is within 1 day of ship_date - order_date", WARN, day_gap > 1),
        ("label_consistency_valid_orders",
         "late_delivery_risk == (shipping_days_real > shipping_days_scheduled) for valid orders",
         ERROR, valid & (f["late_delivery_risk"] != late_from_days)),
        ("label_cancelled_orders_unshipped",
         "Cancelled / fraud orders carry label 0 although real > scheduled days (known source "
         "property; delivery analyses exclude these rows)", WARN,
         ~valid & (f["is_late"] == 1) & (f["late_delivery_risk"] == 0)),
        ("no_duplicate_order_items",
         "No two order items are identical apart from order_item_id", ERROR,
         f.duplicated(subset=dup_cols, keep=False)),
        ("order_level_consistency",
         "Items of one order share timestamps, customer, destination, ship mode, status and label "
         "(needed for order-level modelling)", ERROR, (grouped > 1).any(axis=1)),
    ]  # fmt: skip
    return [_check(n, d, s, "fact_order_items", f, m, k) for n, d, s, m in checks]


def _ck_text(t: dict[str, pd.DataFrame]) -> list[CheckResult]:
    out = []
    for table in ("dim_category", "dim_product", "dim_customer", "dim_geography"):
        df = t[table]
        text = [c for c in df.columns if df[c].dtype == "str" or df[c].dtype == object]
        bad = pd.concat([df[c].str.contains("�|Ã", regex=True) for c in text], axis=1).any(axis=1)
        out.append(
            _check(
                f"no_mojibake__{table}",
                f"No replacement or mis-decoded characters in text columns of {table}",
                WARN,
                table,
                df,
                bad,
                PRIMARY_KEYS[table],
            )
        )
    return out


def _ck_tail(tail: dict | None) -> list[CheckResult]:
    if tail is None:
        return []
    n = tail.get("tail_weeks", 0) if tail.get("abnormal_tail") else 0
    return [
        CheckResult(
            "volume_tail_abnormal",
            "Weekly order volume has no abnormal tail (an abnormal tail is truncated for forecasting)",
            WARN,
            "fact_order_items",
            tail.get("tail_weeks", 0) + 0,
            n,
            [tail["first_abnormal_week"]] if n else [],
        )
    ]


CHECKS: list[Callable[[dict[str, pd.DataFrame]], list[CheckResult]]] = [
    _ck_primary_keys,
    _ck_labels,
    _ck_not_null,
    _ck_foreign_keys,
    _ck_fact,
    _ck_text,
]


def run_checks(tables: dict[str, pd.DataFrame], tail: dict | None = None) -> list[CheckResult]:
    """Run every quality check against the star-schema tables."""
    results: list[CheckResult] = []
    for fn in CHECKS:
        results.extend(fn(tables))
    results.extend(_ck_tail(tail))
    return results


def failures(results: list[CheckResult], severity: str = ERROR) -> list[CheckResult]:
    """Failing checks of the given severity."""
    return [r for r in results if not r.passed and r.severity == severity]


def quality_markdown(results: list[CheckResult], title_note: str = "") -> str:
    """Render reports/data_quality_report.md."""
    n_err = sum(r.severity == ERROR for r in results)
    n_warn = sum(r.severity == WARN for r in results)
    fail_err = len(failures(results, ERROR))
    fail_warn = len(failures(results, WARN))
    lines = [
        "# Data quality report",
        "",
        title_note,
        f"- **{len(results)} checks** ({n_err} error-severity, {n_warn} warn-severity)",
        f"- Failing error checks: **{fail_err}** (the pipeline stops if this is not 0)",
        f"- Failing warn checks: **{fail_warn}** (reported, do not stop the pipeline)",
        "",
        "| Status | Severity | Check | Table | Failing rows | Sample keys |",
        "|---|---|---|---|---:|---|",
    ]
    for r in sorted(results, key=lambda r: (r.passed, r.severity != ERROR, r.name)):
        status = "PASS" if r.passed else ("FAIL" if r.severity == ERROR else "WARN")
        keys = ", ".join(map(str, r.sample_keys)) or "-"
        lines.append(
            f"| {status} | {r.severity} | `{r.name}` | {r.table} | {r.failing_rows:,} "
            f"of {r.total_rows:,} | {keys} |"
        )
    lines += ["", "## Check descriptions", ""]
    lines += [f"- `{r.name}`: {r.description}" for r in results]
    return "\n".join(lines) + "\n"


def write_reports(results: list[CheckResult], reports_dir: Path, note: str = "") -> None:
    """Write the markdown and JSON versions of the quality report."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "data_quality_report.md").write_text(quality_markdown(results, note), encoding="utf-8")
    payload = {
        "n_checks": len(results),
        "n_error_checks": sum(r.severity == ERROR for r in results),
        "n_warn_checks": sum(r.severity == WARN for r in results),
        "failing_errors": len(failures(results, ERROR)),
        "failing_warnings": len(failures(results, WARN)),
        "checks": [{**asdict(r), "passed": r.passed} for r in results],
    }
    (reports_dir / "data_quality_report.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )


def enforce(results: list[CheckResult]) -> None:
    """Raise QualityGateError when any error-severity check failed."""
    bad = failures(results, ERROR)
    if bad:
        names = ", ".join(r.name for r in bad)
        raise QualityGateError(f"{len(bad)} error-severity check(s) failed: {names}")
