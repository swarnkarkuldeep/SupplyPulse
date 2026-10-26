-- id: q01_kpi_month | version: 1
-- Monthly scorecard for the review month and the previous month (valid orders, order level).
SELECT order_month, orders, revenue, profit, margin_pct, on_time_pct, avg_order_value
FROM vw_kpi_monthly
WHERE order_month IN (:month, :prev_month)
