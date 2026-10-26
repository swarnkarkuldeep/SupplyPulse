-- id: q04_margin_by_category | version: 1
-- Sales and profit by category for the review month.
SELECT category_name, SUM(sales) AS sales, SUM(profit) AS profit
FROM vw_margin_analysis
WHERE order_month = :month
GROUP BY category_name
