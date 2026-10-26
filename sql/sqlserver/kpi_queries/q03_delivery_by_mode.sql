-- id: q03_delivery_by_mode | version: 1
-- Orders and late orders by shipping mode for the review month and the previous month.
SELECT order_month, shipping_mode, SUM(orders) AS orders, SUM(late_orders) AS late_orders
FROM vw_delivery_performance
WHERE order_month IN (:month, :prev_month)
GROUP BY order_month, shipping_mode
