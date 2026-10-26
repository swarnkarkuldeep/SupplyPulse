"""Cleaning: raw DataCo columns -> analysis-ready order items and a star schema."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DATE_FORMAT = "%m/%d/%Y %H:%M"

# Columns whose snake_case name needs more than mechanical lower-casing.
RENAMES = {
    "Type": "payment_type",
    "Days for shipping (real)": "shipping_days_real",
    "Days for shipment (scheduled)": "shipping_days_scheduled",
    "Benefit per order": "profit",
    "Sales per customer": "sales_per_customer",
    "Order Item Discount": "discount_amount",
    "Order Item Discount Rate": "discount_rate",
    "Order Item Id": "order_item_id",
    "Order Item Product Price": "unit_price",
    "Order Item Profit Ratio": "profit_ratio",
    "Order Item Quantity": "quantity",
    "Sales": "gross_sales",
    "Order Item Total": "net_sales",
    "Order Profit Per Order": "order_profit_per_order",
    "order date (DateOrders)": "order_ts",
    "shipping date (DateOrders)": "ship_ts",
    "Customer Segment": "segment",
    "Customer Country": "customer_country",
    "Customer State": "customer_state",
    "Customer City": "customer_city",
    "Order Region": "region",
    "Order Country": "country",
}

# Columns dropped because they are personal data (masked or not needed for analytics).
PII_COLUMNS = {
    "customer_email": "PII: masked email, constant value, no analytic use",
    "customer_password": "PII/secret: masked password, constant value",
    "customer_fname": "PII: customer first name",
    "customer_lname": "PII: customer last name",
    "customer_street": "PII: street address",
    "customer_zipcode": "PII-adjacent: postal code, finer than the city/state grain we keep",
}

# Columns dropped for other reasons that are decided by judgement, not measured.
OTHER_DROPS = {
    "product_image": "URL of a product image (1 per product), no analytic use",
    "order_city": "Order-destination city: finer than the market/region/country grain we model",
    "order_state": "Order-destination state: finer than the market/region/country grain we model",
    "latitude": "Coordinates map to neither the customer nor the order city cleanly; unused",
    "longitude": "Coordinates map to neither the customer nor the order city cleanly; unused",
}

# (kept, candidate_to_drop): dropped only if the data proves they are identical.
REDUNDANT_PAIRS = [
    ("customer_id", "order_customer_id"),
    ("product_card_id", "order_item_cardprod_id"),
    ("category_id", "product_category_id"),
    ("profit", "order_profit_per_order"),
    ("net_sales", "sales_per_customer"),
    ("unit_price", "product_price"),
]
# Pair the spec suspected is redundant; we measure it and keep both if it is not.
SUSPECT_PAIRS = [("gross_sales", "net_sales")]

NULL_RATE_DROP = 0.5
COUNTRY_FIXES = {"EE. UU.": "United States"}
INVALID_STATE_PATTERN = r"^\d+$"
EXCLUDED_STATUSES = ("CANCELED", "SUSPECTED_FRAUD")


@dataclass
class CleaningLog:
    """Everything cleaning changed, for reports/cleaning_log.md."""

    rows_raw: int = 0
    rows_clean: int = 0
    dropped_columns: list[tuple[str, str]] = field(default_factory=list)
    kept_pairs: list[tuple[str, str, float]] = field(default_factory=list)
    row_filters: list[tuple[str, int]] = field(default_factory=list)
    value_fixes: list[str] = field(default_factory=list)
    derived: list[tuple[str, str]] = field(default_factory=list)
    dtype_notes: list[str] = field(default_factory=list)


def to_snake(name: str) -> str:
    """'Order Item Id' -> 'order_item_id'."""
    return re.sub(r"[^0-9a-z]+", "_", name.strip().lower()).strip("_")


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename every column to snake_case, using RENAMES for the non-mechanical ones."""
    return df.rename(columns={c: RENAMES.get(c, to_snake(c)) for c in df.columns})


def _tidy_text(s: pd.Series) -> pd.Series:
    """Trim and collapse repeated whitespace."""
    return s.str.strip().str.replace(r"\s+", " ", regex=True)


def drop_columns(df: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Drop PII, redundant and useless columns, logging a reason for each."""
    drops: dict[str, str] = {}
    for col, why in PII_COLUMNS.items():
        if col in df:
            drops[col] = why
    for keep, cand in REDUNDANT_PAIRS + SUSPECT_PAIRS:
        if keep not in df or cand not in df:
            continue
        match = float(np.isclose(df[keep], df[cand], atol=0.005).mean())
        if match == 1.0 and (keep, cand) in REDUNDANT_PAIRS:
            drops[cand] = f"Redundant: identical to `{keep}` in 100% of rows"
        else:
            log.kept_pairs.append((keep, cand, match))
    for col in df.columns:
        if col in drops or col in OTHER_DROPS:
            continue
        null_rate = df[col].isna().mean()
        if null_rate > NULL_RATE_DROP:
            drops[col] = f"{null_rate:.1%} null"
        elif df[col].nunique(dropna=True) <= 1:
            drops[col] = "Constant column (a single distinct value)"
    for col, why in OTHER_DROPS.items():
        if col in df:
            drops[col] = why
    log.dropped_columns = sorted(drops.items())
    return df.drop(columns=list(drops))


def parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Parse order/ship timestamps with an explicit format (month first)."""
    out = df.copy()
    for col in ("order_ts", "ship_ts"):
        out[col] = pd.to_datetime(out[col], format=DATE_FORMAT)
    return out


def standardize_values(df: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Trim/collapse text, fix known label problems and set explicit dtypes."""
    out = df.copy()
    text_cols = [c for c in out.columns if out[c].dtype == "str" or out[c].dtype == object]
    for col in text_cols:
        if col in ("order_ts", "ship_ts"):
            continue
        before = out[col].copy()
        out[col] = _tidy_text(out[col])
        changed = int((before != out[col]).sum())
        if changed:
            log.value_fixes.append(f"`{col}`: trimmed/collapsed whitespace in {changed:,} rows")
    # Two different category ids can share a name (e.g. 'Electronics' under two departments).
    # Suffix the department so a category name always identifies one category.
    ids_per_name = out.groupby("category_name")["category_id"].transform("nunique")
    clash = ids_per_name > 1
    if clash.any():
        names = sorted(out.loc[clash, "category_name"].unique())
        out.loc[clash, "category_name"] = (
            out.loc[clash, "category_name"] + " (" + out.loc[clash, "department_name"] + ")"
        )
        log.value_fixes.append(
            f"`category_name`: {', '.join(names)} each map to several category ids; "
            "department appended to keep names unique"
        )
    fixed = out["customer_country"].isin(COUNTRY_FIXES)
    if fixed.any():
        out.loc[fixed, "customer_country"] = out.loc[fixed, "customer_country"].map(COUNTRY_FIXES)
        log.value_fixes.append(
            f"`customer_country`: 'EE. UU.' (Spanish) -> 'United States' in {int(fixed.sum()):,} rows"
        )
    bad_state = out["customer_state"].str.match(INVALID_STATE_PATTERN)
    if bad_state.any():
        out.loc[bad_state, "customer_state"] = "UNKNOWN"
        log.value_fixes.append(
            f"`customer_state`: zip-code-like values set to 'UNKNOWN' in {int(bad_state.sum())} rows"
        )
    out["order_status"] = out["order_status"].str.upper()
    out["payment_type"] = out["payment_type"].str.upper()
    for col in ("discount_amount", "gross_sales", "net_sales", "profit", "unit_price"):
        out[col] = out[col].astype("float64").round(2)
    out["discount_rate"] = out["discount_rate"].astype("float64").round(4)
    out["profit_ratio"] = out["profit_ratio"].astype("float64").round(4)
    for col in ("quantity", "shipping_days_real", "shipping_days_scheduled", "late_delivery_risk"):
        out[col] = out[col].astype("int64")
    log.dtype_notes.append(
        "Money columns were stored as float32-precision values (e.g. 314.640015); "
        "rounded to 2 decimals. Rates rounded to 4 decimals."
    )
    return out


def derive_fields(df: pd.DataFrame, log: CleaningLog) -> pd.DataFrame:
    """Add date parts, delay, validity flag and margin fields."""
    out = df.copy()
    out["order_date"] = out["order_ts"].dt.normalize()
    out["ship_date"] = out["ship_ts"].dt.normalize()
    out["order_week"] = out["order_date"] - pd.to_timedelta(out["order_date"].dt.day_of_week, unit="D")
    out["order_month"] = out["order_date"].dt.to_period("M").dt.to_timestamp()
    out["shipping_delay_days"] = out["shipping_days_real"] - out["shipping_days_scheduled"]
    out["is_late"] = (out["shipping_delay_days"] > 0).astype("int64")
    out["is_valid_order"] = (~out["order_status"].isin(EXCLUDED_STATUSES)).astype("int64")
    out["cost_amount"] = (out["net_sales"] - out["profit"]).round(2)
    out["profit_per_unit"] = (out["profit"] / out["quantity"]).round(2)
    log.derived = [
        ("order_date, ship_date", "Calendar date of the order / shipment (time removed)"),
        ("order_week", "Monday that starts the order's week (weeks are Monday-Sunday)"),
        ("order_month", "First day of the order's month"),
        ("shipping_delay_days", "shipping_days_real - shipping_days_scheduled"),
        ("is_late", "1 if shipping_delay_days > 0. Only meaningful when is_valid_order = 1"),
        (
            "is_valid_order",
            "0 for CANCELED and SUSPECTED_FRAUD orders, which never shipped; "
            "demand, delivery and margin analyses use is_valid_order = 1",
        ),
        ("cost_amount", "net_sales - profit (implied cost of the item)"),
        ("profit_per_unit", "profit / quantity"),
    ]
    return out


def clean_orders(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningLog]:
    """Run the whole cleaning pipeline on the raw DataCo frame."""
    log = CleaningLog(rows_raw=len(raw))
    df = standardize_columns(raw)
    df = drop_columns(df, log)
    df = parse_dates(df)
    df = standardize_values(df, log)
    dup_ids = df.duplicated(subset="order_item_id", keep="first")
    if dup_ids.any():
        df = df.loc[~dup_ids]
        log.row_filters.append(("Duplicate order_item_id", int(dup_ids.sum())))
    df = derive_fields(df, log)
    n_excl = int((df["is_valid_order"] == 0).sum())
    log.row_filters.append(
        (f"Flagged (kept in the data, is_valid_order = 0): {', '.join(EXCLUDED_STATUSES)}", n_excl)
    )
    df = df.sort_values("order_item_id").reset_index(drop=True)
    log.rows_clean = len(df)
    return df, log


def detect_tail_cutoff(
    order_weeks: pd.Series,
    baseline_weeks: int = 26,
    drop_ratio: float = 0.6,
    min_tail_weeks: int = 4,
) -> dict:
    """Find where weekly order volume permanently collapses.

    ``order_weeks`` holds one Monday-start week per order item. A week is abnormal when its
    count is below ``drop_ratio`` x the median of the ``baseline_weeks`` weeks before it, and
    every later week is also below that level, for at least ``min_tail_weeks`` weeks. The
    final week is dropped from consideration when it holds under half the preceding week (a
    partial week).

    Returns the first abnormal week, the last normal week and the last usable date, or
    ``None`` values when no abnormal tail exists.
    """
    counts = order_weeks.value_counts().sort_index()
    full = pd.date_range(counts.index.min(), counts.index.max(), freq="7D")
    counts = counts.reindex(full, fill_value=0)
    if len(counts) > 1 and counts.iloc[-1] < 0.5 * counts.iloc[-2]:
        counts = counts.iloc[:-1]
    tail_start = None
    for i in range(baseline_weeks // 2, len(counts) - min_tail_weeks + 1):
        # Baseline uses only weeks before the candidate, so the tail cannot pull it down.
        base = counts.iloc[max(0, i - baseline_weeks) : i].median()
        if (counts.iloc[i:] < drop_ratio * base).all():
            tail_start = counts.index[i]
            break
    if tail_start is None:
        return {"abnormal_tail": False, "first_abnormal_week": None, "last_normal_date": None}
    normal = counts[counts.index < tail_start]
    tail = counts[counts.index >= tail_start]
    return {
        "abnormal_tail": True,
        "first_abnormal_week": tail_start.date().isoformat(),
        "last_normal_date": (tail_start - pd.Timedelta(days=1)).date().isoformat(),
        "weekly_median_before": float(normal.iloc[-baseline_weeks:].median()),
        "weekly_median_tail": float(tail.median()),
        "tail_weeks": int(len(tail)),
        "drop_pct": float(1 - tail.median() / normal.iloc[-baseline_weeks:].median()),
    }


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Full calendar table between two dates (inclusive), ready to mark as a Power BI date table."""
    days = pd.date_range(start.normalize(), end.normalize(), freq="D")
    d = pd.DataFrame({"date": days})
    d["date_key"] = (d["date"].dt.year * 10000 + d["date"].dt.month * 100 + d["date"].dt.day).astype("int64")
    d["year"] = d["date"].dt.year
    d["quarter"] = d["date"].dt.quarter
    d["month"] = d["date"].dt.month
    d["month_name"] = d["date"].dt.month_name()
    d["year_month"] = d["date"].dt.strftime("%Y-%m")
    d["week_start"] = d["date"] - pd.to_timedelta(d["date"].dt.day_of_week, unit="D")
    d["iso_week"] = d["date"].dt.isocalendar().week.astype("int64")
    d["day_of_week"] = d["date"].dt.day_of_week + 1
    d["day_name"] = d["date"].dt.day_name()
    d["is_weekend"] = (d["date"].dt.day_of_week >= 5).astype("int64")
    return d[
        [
            "date_key", "date", "year", "quarter", "month", "month_name", "year_month",
            "week_start", "iso_week", "day_of_week", "day_name", "is_weekend",
        ]
    ]  # fmt: skip


def _surrogate(df: pd.DataFrame, natural: list[str], key: str) -> pd.DataFrame:
    """Distinct natural-key rows with a deterministic 1..N surrogate key in first column."""
    dim = df[natural].drop_duplicates().sort_values(natural).reset_index(drop=True)
    dim.insert(0, key, np.arange(1, len(dim) + 1, dtype="int64"))
    return dim


def build_star_schema(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Split the cleaned flat table into fact_order_items and its dimensions."""
    dim_category = _surrogate(
        df, ["category_id", "category_name", "department_id", "department_name"], "category_key"
    )
    prod = (
        df[["product_card_id", "product_name", "category_id", "unit_price"]]
        .drop_duplicates(subset="product_card_id")
        .rename(columns={"unit_price": "list_price"})
        .sort_values("product_card_id")
        .reset_index(drop=True)
    )
    prod = prod.merge(dim_category[["category_key", "category_id"]], on="category_id", how="left")
    prod.insert(0, "product_key", np.arange(1, len(prod) + 1, dtype="int64"))
    dim_product = prod[["product_key", "product_card_id", "product_name", "category_key", "list_price"]]

    cust = df[["customer_id", "segment", "customer_country", "customer_state", "customer_city"]]
    cust = cust.rename(
        columns={"customer_country": "country", "customer_state": "state", "customer_city": "city"}
    ).drop_duplicates(subset="customer_id")
    dim_customer = _surrogate(cust, ["customer_id", "segment", "country", "state", "city"], "customer_key")
    dim_geography = _surrogate(df, ["market", "region", "country"], "geography_key")
    dim_ship = _surrogate(df, ["shipping_mode", "shipping_days_scheduled"], "shipping_mode_key")
    dim_ship = dim_ship.rename(columns={"shipping_days_scheduled": "scheduled_days"})
    dim_date = build_dim_date(
        df["order_date"].min(),
        max(df["ship_date"].max(), df["order_date"].max()) + pd.offsets.YearEnd(0),
    )

    fact = df.merge(dim_category[["category_key", "category_id"]], on="category_id")
    fact = fact.merge(dim_product[["product_key", "product_card_id"]], on="product_card_id")
    fact = fact.merge(dim_customer[["customer_key", "customer_id"]], on="customer_id")
    fact = fact.merge(dim_geography[["geography_key", "market", "region", "country"]],
                      on=["market", "region", "country"])  # fmt: skip
    fact = fact.merge(
        dim_ship.rename(columns={"scheduled_days": "shipping_days_scheduled"})[
            ["shipping_mode_key", "shipping_mode", "shipping_days_scheduled"]
        ],
        on=["shipping_mode", "shipping_days_scheduled"],
    )
    fact["order_date_key"] = _date_key(fact["order_date"])
    fact["ship_date_key"] = _date_key(fact["ship_date"])
    cols = [
        "order_item_id", "order_id", "order_ts", "ship_ts", "order_date_key", "ship_date_key",
        "order_week", "order_month", "customer_key", "product_key", "category_key",
        "geography_key", "shipping_mode_key", "payment_type", "order_status", "delivery_status",
        "quantity", "unit_price", "discount_amount", "discount_rate", "gross_sales", "net_sales",
        "profit", "profit_ratio", "cost_amount", "profit_per_unit", "shipping_days_real",
        "shipping_days_scheduled", "shipping_delay_days", "late_delivery_risk", "is_late",
        "is_valid_order",
    ]  # fmt: skip
    fact = fact[cols].sort_values("order_item_id").reset_index(drop=True)
    return {
        "dim_category": dim_category,
        "dim_product": dim_product,
        "dim_customer": dim_customer,
        "dim_geography": dim_geography,
        "dim_shipping_mode": dim_ship,
        "dim_date": dim_date,
        "fact_order_items": fact,
    }


def _date_key(s: pd.Series) -> pd.Series:
    return (s.dt.year * 10000 + s.dt.month * 100 + s.dt.day).astype("int64")


def cleaning_log_markdown(log: CleaningLog, tail: dict) -> str:
    """Render reports/cleaning_log.md."""
    lines = [
        "# Cleaning log",
        "",
        "Generated by `python -m sca ingest`. Every number comes from the run.",
        "",
    ]
    lines += ["## Row counts", "", "| Stage | Rows |", "|---|---:|"]
    lines += [f"| Raw | {log.rows_raw:,} |", f"| Clean | {log.rows_clean:,} |"]
    lines += [f"| Removed | {log.rows_raw - log.rows_clean:,} |", ""]
    lines += ["## Row filters and flags", "", "| Reason | Rows |", "|---|---:|"]
    lines += [f"| {why} | {n:,} |" for why, n in log.row_filters]
    lines += ["", "No rows were deleted for status reasons; they are flagged so every analysis states "
              "its own treatment (see `is_valid_order`).", ""]  # fmt: skip
    lines += ["## Dropped columns", "", "| Column | Reason |", "|---|---|"]
    lines += [f"| `{c}` | {why} |" for c, why in log.dropped_columns]
    lines += [
        "",
        "## Column pairs checked but kept",
        "",
        "| Pair | Share of rows equal |",
        "|---|---:|",
    ]
    lines += [f"| `{a}` vs `{b}` | {m:.1%} |" for a, b, m in log.kept_pairs]
    lines += ["", "## Value fixes", ""] + [f"- {v}" for v in log.value_fixes]
    lines += ["", "## Data types", ""] + [f"- {v}" for v in log.dtype_notes]
    lines += ["", "## Derived fields", "", "| Field | Definition |", "|---|---|"]
    lines += [f"| `{f}` | {d} |" for f, d in log.derived]
    lines += ["", "## Tail period (abnormal volume)", ""]
    if tail.get("abnormal_tail"):
        lines += [
            f"- Weekly order-item volume falls permanently from week starting "
            f"**{tail['first_abnormal_week']}**: median {tail['weekly_median_before']:,.0f} per week "
            f"(prior 26 weeks) to {tail['weekly_median_tail']:,.0f} ({tail['drop_pct']:.0%} lower) "
            f"for {tail['tail_weeks']} weeks.",
            f"- **Forecasting cutoff: {tail['last_normal_date']}** (last normal day). Rows after it stay "
            "in the database but are excluded from model training and backtests.",
        ]
    else:
        lines += ["- No abnormal tail detected."]
    return "\n".join(lines) + "\n"
