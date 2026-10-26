-- id: q05_forecast_summary | version: 1
-- Total-demand forecast for the future weeks and the champion's backtest accuracy.
SELECT SUM(CASE WHEN kind = 'forecast' THEN forecast END) AS forecast_units,
       COUNT(CASE WHEN kind = 'forecast' THEN 1 END) AS forecast_weeks,
       SUM(CASE WHEN kind = 'backtest' THEN ABS(actual - forecast) END) AS abs_error,
       SUM(CASE WHEN kind = 'backtest' THEN actual END) AS backtest_actual
FROM fct_forecast
WHERE category = 'TOTAL'
