# Dashboard specification

Four report pages at **16:9 (1280 x 720)**, theme `theme.json`. Positions are `x, y, width, height` in pixels on
that canvas. Every visual title is a measure from `dax_measures.md` (Title > fx > Field value), so titles state
the current insight instead of naming the variable. Python versions of these pages are in `reports/figures/dashboard_*.png`.

**Global rules**

- All business measures already exclude cancelled and suspected-fraud orders; do not add a filter for that.
- Slicers sync across pages 1, 3 and 4 (View > Sync slicers). The forecast page has its own category slicer.
- Colours come from the theme (colour-blind-safe Okabe-Ito palette). Do not hard-code colours; use the theme's
  `good`/`bad` colours for deltas.
- Fonts: Segoe UI. Numbers: currency without decimals, percentages with one decimal.

## Page 1 - Executive Scorecard

Question answered: *How are revenue, margin and on-time delivery doing this month, and where is the money?*

| # | Visual | Type | Fields / measures | Filters | Position | Title |
|---|---|---|---|---|---|---|
| 1 | Market | Slicer (dropdown) | `dim_geography[market]` | - | 16, 64, 200, 40 | (none) |
| 2 | Region | Slicer (dropdown) | `dim_geography[region]` | - | 228, 64, 220, 40 | (none) |
| 3 | Date | Slicer (between) | `dim_date[date]` | - | 460, 64, 380, 40 | (none) |
| 4 | Revenue | Card + reference label | `[Total Revenue]`; reference `[Revenue MoM %]` | - | 16, 116, 200, 96 | "Revenue" |
| 5 | Profit | Card + reference label | `[Total Profit]`; reference `[Profit MoM %]` | - | 224, 116, 200, 96 | "Profit" |
| 6 | Margin | Card + reference label | `[Margin %]`; reference `[Margin MoM pp]` | - | 432, 116, 200, 96 | "Margin" |
| 7 | On-time delivery | Card + reference label | `[On-Time Delivery %]`; reference `[On-Time MoM pp]` | - | 640, 116, 200, 96 | "On-time delivery" |
| 8 | Orders | Card + reference label | `[Orders]`; reference `[Orders MoM %]` | - | 848, 116, 200, 96 | "Orders" |
| 9 | Average order value | Card | `[Average Order Value]` | - | 1056, 116, 208, 96 | "Average order value" |
| 10 | Revenue and margin trend | Line and clustered column | X `dim_date[year_month]`; columns `[Total Revenue]`; line (secondary axis) `[Margin %]` | - | 16, 224, 620, 232 | `[Title Revenue Trend]` |
| 11 | On-time trend | Line | X `dim_date[year_month]`; Y `[On-Time Delivery %]` (axis 0-100%) | - | 652, 224, 612, 232 | `[Title On-Time]` |
| 12 | Top categories | Clustered bar | Axis `dim_category[category_name]`; value `[Total Revenue]` | Top N: 5 by `[Total Revenue]` | 16, 468, 620, 236 | `[Title Top Categories]` |
| 13 | Lowest-margin categories | Clustered bar | Axis `dim_category[category_name]`; value `[Margin %]` | Visual filter `[Revenue Share]` >= 0.5%; Top N: bottom 5 by `[Margin %]` | 652, 468, 612, 236 | `[Title Low Margin]` |

Notes: cards 4-8 show the **latest month in the selected date range** (add a card-level filter on
`dim_date[year_month]` = the max, or use a relative-date slicer set to "last 1 month"). The MoM reference labels
only work on the monthly grain.

## Page 2 - Demand Forecast

Question answered: *How much will we sell over the next 12 weeks, and how far can we trust the forecast?*

| # | Visual | Type | Fields / measures | Filters | Position | Title |
|---|---|---|---|---|---|---|
| 1 | Category | Slicer (list, single select) | `fct_forecast[category]` (default `TOTAL`) | - | 16, 64, 240, 300 | (none) |
| 2 | Actual vs forecast | Line chart | X `fct_forecast[week_start]`; lines `[Actual Units]`, `[Forecast Units]`; error band `[Forecast Lower]` / `[Forecast Upper]` | Last 52 weeks of history plus the forecast weeks | 272, 64, 992, 360 | `[Title Forecast]` |
| 3 | Next 12 weeks | Card | `[Forecast Next 12 Weeks]` | - | 16, 376, 240, 88 | "Forecast, next 12 weeks (units)" |
| 4 | Accuracy table | Table | `fct_forecast[category]`, `[Forecast WAPE]`, `[Forecast vs Actual %]`, `[Backtest Actual Units]` | `fct_forecast[category]` is not `TOTAL` | 16, 476, 780, 228 | "Forecast error by category (backtest WAPE, lower is better)" |
| 5 | Accuracy gauge | Gauge | `[Forecast Accuracy %]` (min 0, max 1) | - | 812, 436, 452, 268 | "Backtest accuracy (1 - WAPE)" |

Notes: line chart legend: Actual = grey, Forecast = blue, band = 20% transparent blue. `[Forecast WAPE]` is a
backtest measure, so it ignores future weeks automatically. Add the text "Backtest = out-of-sample forecasts
over the last 40 weeks" under the table.

## Page 3 - Delivery Risk

Question answered: *Which shipments are late, why, and which open orders are most at risk?*

| # | Visual | Type | Fields / measures | Filters | Position | Title |
|---|---|---|---|---|---|---|
| 1 | Market | Slicer (dropdown, synced) | `dim_geography[market]` | - | 16, 64, 200, 40 | (none) |
| 2 | Late % heatmap | Matrix with conditional formatting | Rows `dim_geography[region]`; columns `dim_shipping_mode[shipping_mode]`; values `[Late Delivery %]` (colour scale white to dark orange, 0-100%) | - | 16, 112, 620, 400 | `[Title Delivery Risk]` |
| 3 | Top drivers | Clustered bar | Axis `fct_shap_drivers[feature]`; value `[Driver Share]` | Top N: 8 by `[Driver Share]` | 652, 112, 612, 260 | "What drives predicted lateness (share of model attribution)" |
| 4 | Alert quality | Two cards | `[Alert Precision]`, `[Alert Recall]` | - | 652, 384, 612, 128 | "How good the alerts are (test period)" |
| 5 | Risk-scored recent orders | Table | `fct_late_risk_scores[order_id]`, `order_date`, `shipping_mode`, `region`, `risk_score`, `actual_late` | `split` = test; Top N: 25 by `risk_score`; `risk_score` format 0.00 with data bars | 16, 524, 1248, 180 | "Highest-risk recent orders" |

Notes: the heatmap shows what actually happened; the SHAP chart and table show what the model predicts, which is
why both are on the page. `fct_late_risk_scores` train and validation rows are in-sample: always filter
`split = test`.

## Page 4 - Margin and Discounts (optional)

Question answered: *Where do discounts and losses cost us money?*

| # | Visual | Type | Fields / measures | Filters | Position | Title |
|---|---|---|---|---|---|---|
| 1 | Discount vs profit | Scatter | Details `dim_category[category_name]`; X `[Average Discount %]`; Y `[Margin %]`; size `[Total Revenue]` | - | 16, 64, 620, 380 | `[Title Discount]` |
| 2 | Loss-making combinations | Table | `dim_category[category_name]`, `dim_geography[region]`, `[Loss on Loss-Making Items]`, `[Loss-Making Items %]`, `[Total Revenue]` | Top N: 15 by `[Loss on Loss-Making Items]` (ascending) | 652, 64, 612, 380 | `[Title Losses]` |
| 3 | Margin by region | Clustered bar | Axis `dim_geography[region]`; value `[Margin %]` | - | 16, 456, 1248, 248 | "Margin by region" |

## Accessibility and polish checklist

- Alt text on every visual (Format > General > Alt text).
- Tab order: slicers, cards, charts, tables.
- Check the report in the "Colour blindness" simulator (View > Simulate).
- Hide the `_Measures` table and every `*_key` column in report view.
