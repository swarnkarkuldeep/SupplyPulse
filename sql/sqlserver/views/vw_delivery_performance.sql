-- Grain: shipping mode x region x month. Valid orders only. Rates are at ORDER level:
-- every item of an order shares the same ship date and label, so items would over-weight big orders.
CREATE OR ALTER VIEW vw_delivery_performance AS
WITH orders AS (
    SELECT
        f.order_id,
        f.order_month,
        f.shipping_mode_key,
        f.geography_key,
        MAX(f.is_late) AS is_late,
        MAX(f.shipping_delay_days) AS shipping_delay_days
    FROM fact_order_items AS f
    WHERE f.is_valid_order = 1
    GROUP BY f.order_id, f.order_month, f.shipping_mode_key, f.geography_key
)
SELECT
    s.shipping_mode,
    g.region,
    o.order_month,
    COUNT(*) AS orders,
    SUM(o.is_late) AS late_orders,
    ROUND(100.0 * SUM(o.is_late) / COUNT(*), 2) AS late_pct,
    ROUND(AVG(1.0 * o.shipping_delay_days), 3) AS avg_delay_days
FROM orders AS o
JOIN dim_shipping_mode AS s ON s.shipping_mode_key = o.shipping_mode_key
JOIN dim_geography AS g ON g.geography_key = o.geography_key
GROUP BY s.shipping_mode, g.region, o.order_month;
