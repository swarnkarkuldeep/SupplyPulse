-- id: q07_top_drivers | version: 1
-- Features ranked by their share of the late-delivery model's SHAP attribution.
SELECT feature, share
FROM fct_shap_drivers
ORDER BY mean_abs_shap DESC
