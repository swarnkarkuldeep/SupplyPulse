# Data quality report


- **47 checks** (38 error-severity, 9 warn-severity)
- Failing error checks: **0** (the pipeline stops if this is not 0)
- Failing warn checks: **2** (reported, do not stop the pipeline)

| Status | Severity | Check | Table | Failing rows | Sample keys |
|---|---|---|---|---:|---|
| WARN | warn | `label_cancelled_orders_unshipped` | fact_order_items | 4,423 of 180,519 | 124, 125, 168, 797, 798 |
| WARN | warn | `volume_tail_abnormal` | fact_order_items | 17 of 17 | 2017-10-02 |
| PASS | error | `discount_rate_in_0_1` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `fk__dim_product.category_key->dim_category` | dim_product | 0 of 118 | - |
| PASS | error | `fk__fact_order_items.category_key->dim_category` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `fk__fact_order_items.customer_key->dim_customer` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `fk__fact_order_items.geography_key->dim_geography` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `fk__fact_order_items.order_date_key->dim_date` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `fk__fact_order_items.product_key->dim_product` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `fk__fact_order_items.ship_date_key->dim_date` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `fk__fact_order_items.shipping_mode_key->dim_shipping_mode` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `label_consistency_valid_orders` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `label_unique__dim_category.category_name` | dim_category | 0 of 51 | - |
| PASS | error | `label_unique__dim_product.product_name` | dim_product | 0 of 118 | - |
| PASS | error | `natural_key_unique__dim_category` | dim_category | 0 of 51 | - |
| PASS | error | `natural_key_unique__dim_customer` | dim_customer | 0 of 20,652 | - |
| PASS | error | `natural_key_unique__dim_geography` | dim_geography | 0 of 167 | - |
| PASS | error | `natural_key_unique__dim_product` | dim_product | 0 of 118 | - |
| PASS | error | `natural_key_unique__dim_shipping_mode` | dim_shipping_mode | 0 of 4 | - |
| PASS | error | `no_duplicate_order_items` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `not_null__dim_category` | dim_category | 0 of 51 | - |
| PASS | error | `not_null__dim_customer` | dim_customer | 0 of 20,652 | - |
| PASS | error | `not_null__dim_date` | dim_date | 0 of 1,461 | - |
| PASS | error | `not_null__dim_geography` | dim_geography | 0 of 167 | - |
| PASS | error | `not_null__dim_product` | dim_product | 0 of 118 | - |
| PASS | error | `not_null__dim_shipping_mode` | dim_shipping_mode | 0 of 4 | - |
| PASS | error | `not_null__fact_order_items` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `order_level_consistency` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `pk_unique__dim_category` | dim_category | 0 of 51 | - |
| PASS | error | `pk_unique__dim_customer` | dim_customer | 0 of 20,652 | - |
| PASS | error | `pk_unique__dim_date` | dim_date | 0 of 1,461 | - |
| PASS | error | `pk_unique__dim_geography` | dim_geography | 0 of 167 | - |
| PASS | error | `pk_unique__dim_product` | dim_product | 0 of 118 | - |
| PASS | error | `pk_unique__dim_shipping_mode` | dim_shipping_mode | 0 of 4 | - |
| PASS | error | `pk_unique__fact_order_items` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `prices_non_negative` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `quantity_positive` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `recon_gross_sales` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `recon_net_sales` | fact_order_items | 0 of 180,519 | - |
| PASS | error | `ship_not_before_order` | fact_order_items | 0 of 180,519 | - |
| PASS | warn | `no_mojibake__dim_category` | dim_category | 0 of 51 | - |
| PASS | warn | `no_mojibake__dim_customer` | dim_customer | 0 of 20,652 | - |
| PASS | warn | `no_mojibake__dim_geography` | dim_geography | 0 of 167 | - |
| PASS | warn | `no_mojibake__dim_product` | dim_product | 0 of 118 | - |
| PASS | warn | `recon_discount_rate` | fact_order_items | 0 of 180,519 | - |
| PASS | warn | `recon_profit_ratio` | fact_order_items | 0 of 180,519 | - |
| PASS | warn | `shipping_days_match_dates` | fact_order_items | 0 of 180,519 | - |

## Check descriptions

- `pk_unique__dim_category`: `category_key` is unique and not null in dim_category
- `pk_unique__dim_product`: `product_key` is unique and not null in dim_product
- `pk_unique__dim_customer`: `customer_key` is unique and not null in dim_customer
- `pk_unique__dim_geography`: `geography_key` is unique and not null in dim_geography
- `pk_unique__dim_shipping_mode`: `shipping_mode_key` is unique and not null in dim_shipping_mode
- `pk_unique__dim_date`: `date_key` is unique and not null in dim_date
- `pk_unique__fact_order_items`: `order_item_id` is unique and not null in fact_order_items
- `natural_key_unique__dim_category`: Natural key (category_id) is unique in dim_category
- `natural_key_unique__dim_product`: Natural key (product_card_id) is unique in dim_product
- `natural_key_unique__dim_customer`: Natural key (customer_id) is unique in dim_customer
- `natural_key_unique__dim_geography`: Natural key (market, region, country) is unique in dim_geography
- `natural_key_unique__dim_shipping_mode`: Natural key (shipping_mode) is unique in dim_shipping_mode
- `label_unique__dim_category.category_name`: `category_name` identifies exactly one row of dim_category (needed to forecast by name)
- `label_unique__dim_product.product_name`: `product_name` identifies exactly one row of dim_product (needed to forecast by name)
- `not_null__dim_category`: No nulls in critical columns of dim_category: category_key, category_id, category_name, department_name
- `not_null__dim_product`: No nulls in critical columns of dim_product: product_key, product_card_id, product_name, category_key
- `not_null__dim_customer`: No nulls in critical columns of dim_customer: customer_key, customer_id, segment
- `not_null__dim_geography`: No nulls in critical columns of dim_geography: geography_key, market, region, country
- `not_null__dim_shipping_mode`: No nulls in critical columns of dim_shipping_mode: shipping_mode_key, shipping_mode, scheduled_days
- `not_null__dim_date`: No nulls in critical columns of dim_date: date_key, date
- `not_null__fact_order_items`: No nulls in critical columns of fact_order_items: order_item_id, order_id, order_ts, ship_ts, order_date_key, ship_date_key, customer_key, product_key, category_key, geography_key, shipping_mode_key, quantity, unit_price, discount_rate, gross_sales, net_sales, profit, shipping_days_real, shipping_days_scheduled, late_delivery_risk, is_valid_order
- `fk__fact_order_items.customer_key->dim_customer`: Every fact_order_items.customer_key exists in dim_customer
- `fk__fact_order_items.product_key->dim_product`: Every fact_order_items.product_key exists in dim_product
- `fk__fact_order_items.category_key->dim_category`: Every fact_order_items.category_key exists in dim_category
- `fk__fact_order_items.geography_key->dim_geography`: Every fact_order_items.geography_key exists in dim_geography
- `fk__fact_order_items.shipping_mode_key->dim_shipping_mode`: Every fact_order_items.shipping_mode_key exists in dim_shipping_mode
- `fk__fact_order_items.order_date_key->dim_date`: Every fact_order_items.order_date_key exists in dim_date
- `fk__fact_order_items.ship_date_key->dim_date`: Every fact_order_items.ship_date_key exists in dim_date
- `fk__dim_product.category_key->dim_category`: Every dim_product.category_key exists in dim_category
- `quantity_positive`: quantity > 0
- `discount_rate_in_0_1`: 0 <= discount_rate <= 1
- `prices_non_negative`: unit_price, gross_sales, net_sales and discount_amount are >= 0
- `ship_not_before_order`: ship_ts >= order_ts
- `recon_gross_sales`: gross_sales = unit_price x quantity (tolerance 0.02)
- `recon_net_sales`: net_sales = gross_sales - discount_amount (tolerance 0.02)
- `recon_discount_rate`: discount_amount = discount_rate x gross_sales (rate is rounded to 2 decimals)
- `recon_profit_ratio`: profit_ratio = profit / net_sales (within 0.01)
- `shipping_days_match_dates`: shipping_days_real is within 1 day of ship_date - order_date
- `label_consistency_valid_orders`: late_delivery_risk == (shipping_days_real > shipping_days_scheduled) for valid orders
- `label_cancelled_orders_unshipped`: Cancelled / fraud orders carry label 0 although real > scheduled days (known source property; delivery analyses exclude these rows)
- `no_duplicate_order_items`: No two order items are identical apart from order_item_id
- `order_level_consistency`: Items of one order share timestamps, customer, destination, ship mode, status and label (needed for order-level modelling)
- `no_mojibake__dim_category`: No replacement or mis-decoded characters in text columns of dim_category
- `no_mojibake__dim_product`: No replacement or mis-decoded characters in text columns of dim_product
- `no_mojibake__dim_customer`: No replacement or mis-decoded characters in text columns of dim_customer
- `no_mojibake__dim_geography`: No replacement or mis-decoded characters in text columns of dim_geography
- `volume_tail_abnormal`: Weekly order volume has no abnormal tail (an abnormal tail is truncated for forecasting)
