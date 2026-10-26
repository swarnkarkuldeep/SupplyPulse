-- id: q02_kpi_baseline | version: 1
-- Average of the twelve months before the review month, for "versus the trailing year" comparisons.
SELECT AVG(revenue) AS revenue_avg, AVG(orders) AS orders_avg, AVG(on_time_pct) AS on_time_avg,
       AVG(margin_pct) AS margin_avg, COUNT(*) AS months
FROM vw_kpi_monthly
WHERE order_month >= :base_start AND order_month < :month
