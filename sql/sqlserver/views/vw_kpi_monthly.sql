-- Grain: month. Valid orders only. Order-level CTE first so orders / on-time % / AOV count each
-- order once; LAG then gives month-on-month change.
CREATE OR ALTER VIEW vw_kpi_monthly AS
WITH orders AS (
    SELECT
        f.order_id,
        f.order_month,
        MAX(f.is_late) AS is_late,
        SUM(f.net_sales) AS revenue,
        SUM(f.profit) AS profit
    FROM fact_order_items AS f
    WHERE f.is_valid_order = 1
    GROUP BY f.order_id, f.order_month
),
monthly AS (
    SELECT
        order_month,
        COUNT(*) AS orders,
        SUM(revenue) AS revenue,
        SUM(profit) AS profit,
        ROUND(100.0 * SUM(profit) / NULLIF(SUM(revenue), 0), 2) AS margin_pct,
        ROUND(100.0 * (COUNT(*) - SUM(is_late)) / COUNT(*), 2) AS on_time_pct,
        ROUND(SUM(revenue) / COUNT(*), 2) AS avg_order_value
    FROM orders
    GROUP BY order_month
)
SELECT
    order_month,
    orders,
    revenue,
    profit,
    margin_pct,
    on_time_pct,
    avg_order_value,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY order_month))
          / NULLIF(LAG(revenue) OVER (ORDER BY order_month), 0), 2) AS revenue_mom_pct,
    ROUND(100.0 * (orders - LAG(orders) OVER (ORDER BY order_month))
          / NULLIF(LAG(orders) OVER (ORDER BY order_month), 0), 2) AS orders_mom_pct,
    ROUND(margin_pct - LAG(margin_pct) OVER (ORDER BY order_month), 2) AS margin_mom_pp,
    ROUND(on_time_pct - LAG(on_time_pct) OVER (ORDER BY order_month), 2) AS on_time_mom_pp
FROM monthly;
