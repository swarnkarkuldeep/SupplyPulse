-- Grain: category x region x month. Valid orders only.
-- sales = net_sales (after discount); margin_pct = profit / net_sales.
CREATE OR ALTER VIEW vw_margin_analysis AS
SELECT
    c.category_name,
    g.region,
    f.order_month,
    SUM(f.gross_sales) AS gross_sales,
    SUM(f.net_sales) AS sales,
    SUM(f.profit) AS profit,
    ROUND(100.0 * SUM(f.profit) / NULLIF(SUM(f.net_sales), 0), 2) AS margin_pct,
    ROUND(100.0 * AVG(f.discount_rate), 2) AS avg_discount_pct
FROM fact_order_items AS f
JOIN dim_category AS c ON c.category_key = f.category_key
JOIN dim_geography AS g ON g.geography_key = f.geography_key
WHERE f.is_valid_order = 1
GROUP BY c.category_name, g.region, f.order_month;
