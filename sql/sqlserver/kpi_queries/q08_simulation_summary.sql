-- id: q08_simulation_summary | version: 1
-- Annual holding cost at the lower and higher simulated service targets, all categories.
SELECT COUNT(*) AS categories, SUM(holding_cost_from) AS cost_from, SUM(holding_cost_to) AS cost_to
FROM fct_simulation_recommendations
WHERE holding_cost_to IS NOT NULL
