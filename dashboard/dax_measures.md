# DAX measures

Paste each measure into the model (Home > New measure, or the table `_Measures`, see `BUILD_GUIDE.md`).
Table and column names are exactly those loaded from the database. `tests/test_dashboard_assets.py` checks that
every `table[column]` below exists and every `[Measure]` reference is defined in this file.

**Conventions**

- Every business measure counts **valid orders only** (`is_valid_order = 1`), which excludes cancelled and
  suspected-fraud orders, exactly like the SQL views (`vw_kpi_monthly` and friends).
- Order-level measures (orders, late orders, on-time %, delay) count each order once, never each item.
- Time intelligence needs `dim_date` marked as the date table (column `date`) and the active relationship
  `fact_order_items[order_date_key]` to `dim_date[date_key]`.

## Revenue, profit and volume

### Total Revenue
```dax
Total Revenue =
CALCULATE ( SUM ( fact_order_items[net_sales] ), fact_order_items[is_valid_order] = 1 )
```
Net sales after discount, valid orders only.

### Gross Sales
```dax
Gross Sales =
CALCULATE ( SUM ( fact_order_items[gross_sales] ), fact_order_items[is_valid_order] = 1 )
```
Sales at list price, before discount.

### Discount Amount
```dax
Discount Amount =
CALCULATE ( SUM ( fact_order_items[discount_amount] ), fact_order_items[is_valid_order] = 1 )
```
Money given away in discounts.

### Average Discount %
```dax
Average Discount % =
DIVIDE ( [Discount Amount], [Gross Sales] )
```
Discount as a share of list-price sales.

### Total Profit
```dax
Total Profit =
CALCULATE ( SUM ( fact_order_items[profit] ), fact_order_items[is_valid_order] = 1 )
```
Profit per the source data (can be negative).

### Margin %
```dax
Margin % =
DIVIDE ( [Total Profit], [Total Revenue] )
```
Profit as a share of net sales.

### Units Sold
```dax
Units Sold =
CALCULATE ( SUM ( fact_order_items[quantity] ), fact_order_items[is_valid_order] = 1 )
```
Units on valid orders; the demand measure used by the forecast.

### Orders
```dax
Orders =
CALCULATE ( DISTINCTCOUNT ( fact_order_items[order_id] ), fact_order_items[is_valid_order] = 1 )
```
Distinct valid orders.

### Average Order Value
```dax
Average Order Value =
DIVIDE ( [Total Revenue], [Orders] )
```
Net revenue per order.

### Loss-Making Items %
```dax
Loss-Making Items % =
DIVIDE (
    CALCULATE ( COUNTROWS ( fact_order_items ), fact_order_items[is_valid_order] = 1, fact_order_items[profit] < 0 ),
    CALCULATE ( COUNTROWS ( fact_order_items ), fact_order_items[is_valid_order] = 1 )
)
```
Share of items sold at a loss.

### Loss on Loss-Making Items
```dax
Loss on Loss-Making Items =
CALCULATE (
    SUM ( fact_order_items[profit] ),
    fact_order_items[is_valid_order] = 1,
    fact_order_items[profit] < 0
)
```
Total (negative) profit of loss-making items.

### Cancelled or Fraud Items %
```dax
Cancelled or Fraud Items % =
DIVIDE (
    CALCULATE ( COUNTROWS ( fact_order_items ), fact_order_items[is_valid_order] = 0 ),
    COUNTROWS ( fact_order_items )
)
```
Share of items excluded from every other measure.

### Revenue Share
```dax
Revenue Share =
DIVIDE ( [Total Revenue], CALCULATE ( [Total Revenue], ALLSELECTED ( dim_category ) ) )
```
A category's share of the revenue in the current selection; used to ignore tiny categories when ranking margins.

### Top 5 Revenue Share
```dax
Top 5 Revenue Share =
DIVIDE (
    SUMX ( TOPN ( 5, ALLSELECTED ( dim_category[category_name] ), [Total Revenue] ), [Total Revenue] ),
    CALCULATE ( [Total Revenue], ALLSELECTED ( dim_category ) )
)
```
Share of revenue brought by the five biggest categories.

## Delivery

### Late Orders
```dax
Late Orders =
CALCULATE (
    DISTINCTCOUNT ( fact_order_items[order_id] ),
    fact_order_items[is_valid_order] = 1,
    fact_order_items[is_late] = 1
)
```
Orders shipped after the scheduled days.

### On-Time Delivery %
```dax
On-Time Delivery % =
DIVIDE ( [Orders] - [Late Orders], [Orders] )
```
Share of orders that shipped on or before schedule.

### Late Delivery %
```dax
Late Delivery % =
1 - [On-Time Delivery %]
```
The complement, used in the risk heatmap.

### Average Delay Days
```dax
Average Delay Days =
CALCULATE (
    AVERAGEX (
        VALUES ( fact_order_items[order_id] ),
        CALCULATE ( MAX ( fact_order_items[shipping_delay_days] ) )
    ),
    fact_order_items[is_valid_order] = 1
)
```
Mean of (real minus scheduled shipping days) per order; negative means early. Computed per order, not per item.

## Time intelligence

### Revenue PM
```dax
Revenue PM =
CALCULATE ( [Total Revenue], DATEADD ( dim_date[date], -1, MONTH ) )
```
Revenue in the previous month.

### Revenue MoM %
```dax
Revenue MoM % =
DIVIDE ( [Total Revenue] - [Revenue PM], [Revenue PM] )
```
Month-on-month change in revenue.

### Revenue LY
```dax
Revenue LY =
CALCULATE ( [Total Revenue], SAMEPERIODLASTYEAR ( dim_date[date] ) )
```
Revenue in the same period a year earlier.

### Revenue YoY %
```dax
Revenue YoY % =
DIVIDE ( [Total Revenue] - [Revenue LY], [Revenue LY] )
```
Year-on-year change in revenue.

### Revenue YTD
```dax
Revenue YTD =
TOTALYTD ( [Total Revenue], dim_date[date] )
```
Year-to-date revenue.

### Profit MoM %
```dax
Profit MoM % =
DIVIDE (
    [Total Profit] - CALCULATE ( [Total Profit], DATEADD ( dim_date[date], -1, MONTH ) ),
    CALCULATE ( [Total Profit], DATEADD ( dim_date[date], -1, MONTH ) )
)
```
Month-on-month change in profit.

### Orders MoM %
```dax
Orders MoM % =
DIVIDE (
    [Orders] - CALCULATE ( [Orders], DATEADD ( dim_date[date], -1, MONTH ) ),
    CALCULATE ( [Orders], DATEADD ( dim_date[date], -1, MONTH ) )
)
```
Month-on-month change in order count.

### Margin MoM pp
```dax
Margin MoM pp =
( [Margin %] - CALCULATE ( [Margin %], DATEADD ( dim_date[date], -1, MONTH ) ) ) * 100
```
Month-on-month change in margin, in percentage points.

### On-Time MoM pp
```dax
On-Time MoM pp =
( [On-Time Delivery %] - CALCULATE ( [On-Time Delivery %], DATEADD ( dim_date[date], -1, MONTH ) ) ) * 100
```
Month-on-month change in on-time delivery, in percentage points.

## Forecast (`fct_forecast`)

`kind` is `history` (actuals), `backtest` (the champion's out-of-sample forecasts with their actuals) or `forecast` (future weeks).

### Actual Units
```dax
Actual Units =
CALCULATE ( SUM ( fct_forecast[actual] ), fct_forecast[kind] = "history" )
```
Observed weekly units.

### Forecast Units
```dax
Forecast Units =
CALCULATE ( SUM ( fct_forecast[forecast] ), fct_forecast[kind] IN { "backtest", "forecast" } )
```
Forecast units for backtest and future weeks.

### Forecast Lower
```dax
Forecast Lower =
CALCULATE ( SUM ( fct_forecast[lower] ), fct_forecast[kind] IN { "backtest", "forecast" } )
```
Lower bound of the 80% prediction interval.

### Forecast Upper
```dax
Forecast Upper =
CALCULATE ( SUM ( fct_forecast[upper] ), fct_forecast[kind] IN { "backtest", "forecast" } )
```
Upper bound of the 80% prediction interval.

### Backtest Actual Units
```dax
Backtest Actual Units =
CALCULATE ( SUM ( fct_forecast[actual] ), fct_forecast[kind] = "backtest" )
```
Actual units over the backtest weeks.

### Backtest Abs Error
```dax
Backtest Abs Error =
SUMX (
    FILTER ( fct_forecast, fct_forecast[kind] = "backtest" ),
    ABS ( fct_forecast[actual] - fct_forecast[forecast] )
)
```
Sum of absolute forecast errors over the backtest weeks.

### Forecast WAPE
```dax
Forecast WAPE =
DIVIDE ( [Backtest Abs Error], [Backtest Actual Units] )
```
Weighted absolute percentage error of the backtest (lower is better); the primary accuracy metric.

### Forecast Accuracy %
```dax
Forecast Accuracy % =
1 - [Forecast WAPE]
```
The complement of WAPE, for a gauge or card.

### Forecast vs Actual %
```dax
Forecast vs Actual % =
DIVIDE (
    CALCULATE ( SUM ( fct_forecast[forecast] ), fct_forecast[kind] = "backtest" ) - [Backtest Actual Units],
    [Backtest Actual Units]
)
```
Forecast bias over the backtest: positive means over-forecasting.

### Forecast Next 12 Weeks
```dax
Forecast Next 12 Weeks =
CALCULATE ( SUM ( fct_forecast[forecast] ), fct_forecast[kind] = "forecast" )
```
Total forecast units over the future weeks.

## Delivery risk (`fct_late_risk_scores`, `fct_shap_drivers`)

Scores for `train` and `validation` orders are in-sample; the dashboard shows `split = "test"` only.

### Orders Scored
```dax
Orders Scored =
CALCULATE ( DISTINCTCOUNT ( fct_late_risk_scores[order_id] ), fct_late_risk_scores[split] = "test" )
```
Test-period orders with a risk score.

### Average Risk Score
```dax
Average Risk Score =
CALCULATE ( AVERAGE ( fct_late_risk_scores[risk_score] ), fct_late_risk_scores[split] = "test" )
```
Mean predicted probability of late delivery.

### High-Risk Orders
```dax
High-Risk Orders =
CALCULATE (
    DISTINCTCOUNT ( fct_late_risk_scores[order_id] ),
    fct_late_risk_scores[split] = "test",
    fct_late_risk_scores[predicted_late] = 1
)
```
Orders the model flags as likely late.

### Alert Precision
```dax
Alert Precision =
DIVIDE (
    CALCULATE (
        COUNTROWS ( fct_late_risk_scores ),
        fct_late_risk_scores[split] = "test",
        fct_late_risk_scores[predicted_late] = 1,
        fct_late_risk_scores[actual_late] = 1
    ),
    [High-Risk Orders]
)
```
Of the orders flagged, the share that really were late.

### Alert Recall
```dax
Alert Recall =
DIVIDE (
    CALCULATE (
        COUNTROWS ( fct_late_risk_scores ),
        fct_late_risk_scores[split] = "test",
        fct_late_risk_scores[predicted_late] = 1,
        fct_late_risk_scores[actual_late] = 1
    ),
    CALCULATE (
        COUNTROWS ( fct_late_risk_scores ),
        fct_late_risk_scores[split] = "test",
        fct_late_risk_scores[actual_late] = 1
    )
)
```
Of the orders that were late, the share the model flagged.

### Driver Share
```dax
Driver Share =
SUM ( fct_shap_drivers[share] )
```
Share of the model's attribution (SHAP) a feature accounts for; use with `fct_shap_drivers[feature]`.

## Inventory simulation (`fct_simulation_results`, `fct_simulation_recommendations`)

Use these with a single category selected, or a table visual by category.

### Simulated Stockout Risk
```dax
Simulated Stockout Risk =
AVERAGE ( fct_simulation_results[p_any_stockout] )
```
Probability of at least one stockout in 52 weeks.

### Simulated Service Level
```dax
Simulated Service Level =
AVERAGE ( fct_simulation_results[cycle_service_level] )
```
Share of weeks without a stockout.

### Simulated Holding Cost
```dax
Simulated Holding Cost =
SUM ( fct_simulation_results[holding_cost] )
```
Annual holding cost of the selected stock level(s).

### Recommended Safety Stock
```dax
Recommended Safety Stock =
SUM ( fct_simulation_recommendations[to_stock] )
```
Safety stock units that reach the higher simulated service target.

## Dynamic titles (visual titles that state the insight)

Use as Title > fx > Field value on the visual named in `dashboard_spec.md`.

### Title Revenue Trend
```dax
Title Revenue Trend =
"Revenue is " & FORMAT ( [Total Revenue], "$#,##0" ) & " ("
    & FORMAT ( [Revenue MoM %], "+0.0%;-0.0%" ) & " vs last month), margin "
    & FORMAT ( [Margin %], "0.0%" )
```
Headline for the revenue and margin trend.

### Title On-Time
```dax
Title On-Time =
FORMAT ( [On-Time Delivery %], "0%" ) & " of orders ship on time; "
    & FORMAT ( [Late Orders], "#,##0" ) & " were late"
```
Headline for the on-time trend.

### Title Forecast
```dax
Title Forecast =
"Next 12 weeks: " & FORMAT ( [Forecast Next 12 Weeks], "#,##0" ) & " units; backtest WAPE "
    & FORMAT ( [Forecast WAPE], "0.0%" )
```
Headline for the forecast chart.

### Title Delivery Risk
```dax
Title Delivery Risk =
FORMAT ( [Late Delivery %], "0%" ) & " of orders are late; the model flags "
    & FORMAT ( [High-Risk Orders], "#,##0" ) & " test orders with "
    & FORMAT ( [Alert Precision], "0%" ) & " precision"
```
Headline for the delivery-risk page.

### Title Discount
```dax
Title Discount =
"Discounts give away " & FORMAT ( [Discount Amount], "$#,##0" ) & " ("
    & FORMAT ( [Average Discount %], "0.0%" ) & " of list sales)"
```
Headline for the margin and discount page.

### Title Losses
```dax
Title Losses =
FORMAT ( [Loss-Making Items %], "0%" ) & " of items lose money, "
    & FORMAT ( ABS ( [Loss on Loss-Making Items] ), "$#,##0" ) & " in total"
```
Headline for the loss-making combinations.

### Title Top Categories
```dax
Title Top Categories =
"Top 5 categories bring " & FORMAT ( [Top 5 Revenue Share], "0%" ) & " of revenue"
```
Headline for the top-categories bar chart.

### Title Low Margin
```dax
Title Low Margin =
"Lowest-margin categories: " & FORMAT ( [Margin %], "0.0%" ) & " overall, spread shown by category"
```
Headline for the low-margin bar chart (filtered to categories with a material revenue share).
