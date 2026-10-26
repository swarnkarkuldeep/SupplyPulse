-- Grain: category x week. Valid orders only (cancelled / suspected-fraud excluded).
-- Weeks with no sales have no row; the Python forecasting code fills them with zero.
CREATE OR ALTER VIEW vw_weekly_demand AS
WITH weekly AS (
    SELECT
        c.category_name,
        c.department_name,
        f.order_week AS week_start,
        SUM(f.quantity) AS units,
        SUM(f.net_sales) AS sales,
        COUNT(DISTINCT f.order_id) AS orders
    FROM fact_order_items AS f
    JOIN dim_category AS c ON c.category_key = f.category_key
    WHERE f.is_valid_order = 1
    GROUP BY c.category_name, c.department_name, f.order_week
)
SELECT
    category_name,
    department_name,
    week_start,
    units,
    sales,
    orders,
    RANK() OVER (PARTITION BY week_start ORDER BY units DESC) AS units_rank_in_week
FROM weekly;
