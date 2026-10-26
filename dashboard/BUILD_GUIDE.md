# Power BI build guide

Build the four-page report in about a day. You need **Power BI Desktop** (Windows). Everything the report needs is
prepared in the repo: the data in SQL Server (or Parquet/CSV files), the measures, the theme and the page specs.

Contents of this folder:

| File | Use |
|---|---|
| `dax_measures.md` | Every measure, ready to paste |
| `theme.json` | Report theme (colour-blind-safe palette) |
| `dashboard_spec.md` | Page-by-page visual list with fields, filters, positions and titles |
| `reconciliation.md` | The numbers your cards must show (generated, no slicers applied) |
| `data/` | Parquet and CSV copies of every table (git-ignored; regenerate with `python -m sca kpis`) |
| `screenshots/` | Put your exported page images here |

## 0. Prepare the data

```powershell
.\.venv\Scripts\Activate.ps1
python -m sca all            # builds everything (SQLite by default)
```

To load into SQL Server instead:

1. Copy `.env.example` to `.env`, set `DB_BACKEND=sqlserver`, `MSSQL_SA_PASSWORD=<strong password>` and
   `DB_PASSWORD=<the same password>`.
2. `docker compose up -d` and wait until `docker compose ps` shows `healthy`.
3. Install **ODBC Driver 18 for SQL Server** (needed by Python's `pyodbc`, not by Power BI).
4. `python -m sca all` (the `load`, `forecast`, `risk` and `simulate` stages each write their tables).
   `python -m sca kpis` refreshes `dashboard/data/` and the reconciliation numbers.

## 1. Connect to SQL Server

1. Home > Get data > SQL Server.
2. Server: `localhost,1433`, Database: `supplypulse`, mode **Import**.
3. Choose **Database** credentials: user `sa`, the password from `.env`.
4. Local Docker uses a self-signed certificate. If Power BI refuses to connect, untick *Encrypt connections*
   in the connection dialog (or trust the server certificate); this is only acceptable for local Docker.
5. Select these tables (not the views): `fact_order_items`, `dim_date`, `dim_category`, `dim_product`,
   `dim_customer`, `dim_geography`, `dim_shipping_mode`, `fct_forecast`, `fct_late_risk_scores`,
   `fct_shap_drivers`, `fct_simulation_results`, `fct_simulation_recommendations`. Load.

**No SQL Server?** Use Get data > Parquet (or Text/CSV) and load the same table names from `dashboard/data/`.
Name each query exactly like the table (the DAX uses these names).

## 2. Set up relationships (Model view)

Create these, all **many-to-one, single direction**:

| From (many) | To (one) | Active |
|---|---|---|
| `fact_order_items[order_date_key]` | `dim_date[date_key]` | yes |
| `fact_order_items[ship_date_key]` | `dim_date[date_key]` | no (inactive) |
| `fact_order_items[category_key]` | `dim_category[category_key]` | yes |
| `fact_order_items[product_key]` | `dim_product[product_key]` | yes |
| `fact_order_items[customer_key]` | `dim_customer[customer_key]` | yes |
| `fact_order_items[geography_key]` | `dim_geography[geography_key]` | yes |
| `fact_order_items[shipping_mode_key]` | `dim_shipping_mode[shipping_mode_key]` | yes |
| `fct_forecast[week_start]` | `dim_date[date]` | yes |
| `fct_late_risk_scores[order_date]` | `dim_date[date]` | yes |
| `fct_simulation_results[category]` | `dim_category[category_name]` | yes |
| `fct_simulation_recommendations[category]` | `dim_category[category_name]` | yes |

Do **not** relate `dim_product` to `dim_category` (it would create a second path from the fact table; the
category is already on the fact). `fct_shap_drivers` has no relationships. In `fct_forecast`, the `TOTAL` series
has no matching category: use `fct_forecast[category]` directly in slicers and visuals on page 2.

## 3. Mark the date table

Select `dim_date` > Table tools > **Mark as date table** > choose column `date`. Set `date` to Date type,
and sort `month_name` by `month` and `day_name` by `day_of_week` (Column tools > Sort by column).

## 4. Import the theme

View > Themes > **Browse for themes** > `dashboard/theme.json`.

## 5. Create the measures

1. Home > Enter data > create an empty table named `_Measures` (delete the blank column afterwards).
2. For each measure in `dax_measures.md`: select `_Measures` > New measure > paste the code block.
   The code block is the complete `Name = ...` formula.
3. Set formats: `%` measures to Percentage (1 decimal), revenue/profit to Currency (0 decimals), counts to
   whole number.
4. Hide `_Measures` from the field list columns but keep the measures visible.

## 6. Build each page

Follow `dashboard_spec.md` page by page (positions, fields, filters and the title measure for each visual).
Order that works well:

1. Page 1: slicers, then the six cards, then the four charts.
2. Page 2: the line chart first (it sets the story), then the table and gauge.
3. Page 3: matrix heatmap with conditional formatting (Format > Cell elements > Background colour > fx).
4. Page 4 (optional).

## 7. Check the numbers

With **no slicers applied** the cards must match `reconciliation.md`
(for example `[Total Revenue]`, `[Orders]` and `[On-Time Delivery %]`). If they do not:

- Revenue too high: a measure is missing the `is_valid_order = 1` filter.
- Orders too high: a measure counts items instead of distinct `order_id`.
- Time-intelligence blank: `dim_date` is not marked, or the relationship is on `ship_date_key`.

## 8. Export

- Screenshots: File > Export > **Export to PDF** for the report, plus one PNG per page (View > Performance
  analyzer is not needed; use Windows Snipping Tool at 100% zoom). Save to `dashboard/screenshots/`
  as `page1_scorecard.png`, `page2_forecast.png`, `page3_delivery_risk.png`, `page4_margin.png`.
- Save the report as `SupplyPulse.pbix` **outside the repo** (it is large and contains data), or add it to
  `.gitignore` first.
- Update the README's dashboard section with the screenshots.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Cannot connect" to `localhost,1433` | `docker compose ps` must show `healthy`; the SA password in Power BI must match `.env`. |
| `fct_forecast` totals look doubled | A visual sums `actual` across `history` and `backtest` rows; use `[Actual Units]`, which filters to `history`. |
| Risk page shows near-perfect precision | The table includes `train` rows (in-sample); filter `split = test`. |
| Slow `[Average Delay Days]` | It iterates orders; use it in cards or small visuals, not a 60k-row table. |
