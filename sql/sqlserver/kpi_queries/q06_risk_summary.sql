-- id: q06_risk_summary | version: 1
-- Late-delivery alerts on the held-out test period.
SELECT COUNT(*) AS orders,
       SUM(predicted_late) AS flagged,
       SUM(CASE WHEN predicted_late = 1 AND actual_late = 1 THEN 1 ELSE 0 END) AS true_positives,
       SUM(actual_late) AS late
FROM fct_late_risk_scores
WHERE split = 'test'
