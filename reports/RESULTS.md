# Results

Every number below was computed by code in this repository and read from the files named in the last column (regenerate with `python -m sca results`). Nothing is illustrative.

| Metric | Value | How computed | Source file |
|---|---|---|---|
| Raw rows | 180,519 | Rows in the Kaggle CSV | `reports/data_profile.md` |
| Clean rows | 180,519 | After cleaning; no rows deleted (cancelled and fraud orders are flagged) | `reports/cleaning_log.md` |
| Data-quality checks | 47 (38 error, 9 warn) | Checks in `quality.py`; 0 error-severity failures, 2 warnings | `reports/data_quality_report.json` |
| Forecast cutoff | 2017-10-01 | Last normal day before weekly volume drops 60% | `reports/cleaning_log.md` |
| Categories forecast (top-N) | 9 | Top categories by units with at most 5% zero weeks and 100+ weeks of history | `reports/forecast_results.md` |
| Champion forecast model | SARIMA | Lowest pooled WAPE over 5 rolling-origin folds of 8 weeks | `reports/forecast_results.md` |
| Forecast WAPE | 8.1% | Sum of absolute errors / sum of actuals, pooled over categories and folds | `data/processed/forecast/metrics_overall.csv` |
| Forecast MAPE | 8.5% | Mean absolute percentage error over non-zero weeks | `data/processed/forecast/metrics_overall.csv` |
| Improvement over seasonal naive | 23.4% | (WAPE naive 10.6% - WAPE champion) / WAPE naive | `reports/forecast_results.md` |
| Champion vs moving average | 0.2 pp | WAPE moving average 8.3%; within backtest noise | `reports/forecast_results.md` |
| Late-risk ROC-AUC (test) | 0.778 | lightgbm, time-based split, most recent 20% of orders | `reports/risk_model_results.md` |
| Late-risk PR-AUC (test) | 0.859 | Base rate 57.4% late | `reports/risk_model_results.md` |
| Shipping-mode-only ROC-AUC | 0.744 | Baseline using only the shipping mode's historical late rate | `reports/risk_model_results.md` |
| Late alerts: precision / recall | 89.7% / 58.9% | At the threshold chosen on validation data (1:1 miss to false-alarm cost) | `reports/risk_model_results.md` |
| Simulated stockout risk, before to after | 99% to 39% | Mean over categories of P(at least one stockout in 52 weeks): cheapest stock reaching 90% vs 98% simulated cycle service | `reports/simulation_results.md` |
| Holding cost change | +35% | $36,011 to $48,792 per year across categories (assumed cost and holding rate) | `reports/simulation_results.md` |
| Textbook safety stock, simulated service at a 95% target | 82.9% | 10,000 paths x 52 weeks with random supplier lead times | `reports/simulation_results.md` |
| DAX measures | 55 | Measure definitions in the DAX file (tested against the schema) | `dashboard/dax_measures.md` |
| Tests | 203 | pytest test cases collected | `tests/` |
| Revenue / profit / margin | $31,644,665 / $3,806,421 / 12.0% | Valid orders only | `dashboard/reconciliation.md` |
| On-time delivery | 42.7% | 62,897 valid orders | `dashboard/reconciliation.md` |
| Loss-making items | 18.7% | Wipe out 49% of gross profit; 10 products hold 90% of the loss | `reports/eda_findings.md` |
| Discount vs margin (OLS) | -0.010 pp per +1 pp, p = 0.54 | HC3 robust SEs, controls for category/region/ship mode; R-squared 0.000; associational | `reports/eda_findings.md` |

## Which forecast metric to quote: WAPE

Quote **WAPE** (8.1% for the champion; MAPE is 8.5%). WAPE weights every unit equally, so busy categories count more than quiet ones, and it stays defined when a week has zero sales. MAPE divides by each week's actual, so small or zero weeks blow it up (16% of weeks are zero in the first categories that were too sparse to forecast) and it cannot be pooled safely. On this dataset the two numbers are close for the selected categories, but WAPE is the number that will stay stable if the category mix changes.

## Wording that is safe on a CV

- Cleaned and validated 180,519 order items with 47 automated data-quality checks (no error-severity failures).
- Forecast weekly demand for 9 categories with rolling-origin backtests; the best model cut error 23% versus a seasonal-naive baseline (WAPE 8.1%), although a simple moving average was only 0.2 pp behind.
- Built a leakage-guarded late-delivery model (test ROC-AUC 0.78) and showed that shipping mode alone gets 0.74.
- Showed by Monte Carlo simulation that textbook safety stock delivers 83% service against a 95% target once supplier lead times vary.

Do not claim: a Power BI report was built (the assets are ready, the `.pbix` is yours to build), or that a Gemini or Groq generated review pack exists (see the README limitations).
