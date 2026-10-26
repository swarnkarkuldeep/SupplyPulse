-- Star schema for SQLite (tests, CI, SQL-Server-free runs). Same tables and keys as sqlserver/schema.sql.
-- Statements are separated by a semicolon at the end of a line.

CREATE TABLE IF NOT EXISTS dim_category (
    category_key    INTEGER NOT NULL PRIMARY KEY,
    category_id     INTEGER NOT NULL UNIQUE,
    category_name   TEXT    NOT NULL,
    department_id   INTEGER NOT NULL,
    department_name TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_product (
    product_key     INTEGER NOT NULL PRIMARY KEY,
    product_card_id INTEGER NOT NULL UNIQUE,
    product_name    TEXT    NOT NULL,
    category_key    INTEGER NOT NULL REFERENCES dim_category (category_key),
    list_price      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
    customer_key INTEGER NOT NULL PRIMARY KEY,
    customer_id  INTEGER NOT NULL UNIQUE,
    segment      TEXT    NOT NULL,
    country      TEXT,
    state        TEXT,
    city         TEXT
);

CREATE TABLE IF NOT EXISTS dim_geography (
    geography_key INTEGER NOT NULL PRIMARY KEY,
    market        TEXT    NOT NULL,
    region        TEXT    NOT NULL,
    country       TEXT    NOT NULL,
    UNIQUE (market, region, country)
);

CREATE TABLE IF NOT EXISTS dim_shipping_mode (
    shipping_mode_key INTEGER NOT NULL PRIMARY KEY,
    shipping_mode     TEXT    NOT NULL UNIQUE,
    scheduled_days    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key    INTEGER NOT NULL PRIMARY KEY,
    date        DATE    NOT NULL UNIQUE,
    year        INTEGER NOT NULL,
    quarter     INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    month_name  TEXT    NOT NULL,
    year_month  TEXT    NOT NULL,
    week_start  DATE    NOT NULL,
    iso_week    INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name    TEXT    NOT NULL,
    is_weekend  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_order_items (
    order_item_id           INTEGER  NOT NULL PRIMARY KEY,
    order_id                INTEGER  NOT NULL,
    order_ts                DATETIME NOT NULL,
    ship_ts                 DATETIME NOT NULL,
    order_date_key          INTEGER  NOT NULL REFERENCES dim_date (date_key),
    ship_date_key           INTEGER  NOT NULL REFERENCES dim_date (date_key),
    order_week              DATE     NOT NULL,
    order_month             DATE     NOT NULL,
    customer_key            INTEGER  NOT NULL REFERENCES dim_customer (customer_key),
    product_key             INTEGER  NOT NULL REFERENCES dim_product (product_key),
    category_key            INTEGER  NOT NULL REFERENCES dim_category (category_key),
    geography_key           INTEGER  NOT NULL REFERENCES dim_geography (geography_key),
    shipping_mode_key       INTEGER  NOT NULL REFERENCES dim_shipping_mode (shipping_mode_key),
    payment_type            TEXT     NOT NULL,
    order_status            TEXT     NOT NULL,
    delivery_status         TEXT     NOT NULL,
    quantity                INTEGER  NOT NULL,
    unit_price              REAL     NOT NULL,
    discount_amount         REAL     NOT NULL,
    discount_rate           REAL     NOT NULL,
    gross_sales             REAL     NOT NULL,
    net_sales               REAL     NOT NULL,
    profit                  REAL     NOT NULL,
    profit_ratio            REAL     NOT NULL,
    cost_amount             REAL     NOT NULL,
    profit_per_unit         REAL     NOT NULL,
    shipping_days_real      INTEGER  NOT NULL,
    shipping_days_scheduled INTEGER  NOT NULL,
    shipping_delay_days     INTEGER  NOT NULL,
    late_delivery_risk      INTEGER  NOT NULL,
    is_late                 INTEGER  NOT NULL,
    is_valid_order          INTEGER  NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_fact_order_id ON fact_order_items (order_id);

CREATE INDEX IF NOT EXISTS ix_fact_order_week_category ON fact_order_items (order_week, category_key);

CREATE INDEX IF NOT EXISTS ix_fact_order_month ON fact_order_items (order_month);

CREATE INDEX IF NOT EXISTS ix_fact_geography ON fact_order_items (geography_key);

CREATE INDEX IF NOT EXISTS ix_fact_shipping_mode ON fact_order_items (shipping_mode_key);

CREATE INDEX IF NOT EXISTS ix_fact_customer ON fact_order_items (customer_key);

CREATE INDEX IF NOT EXISTS ix_fact_product ON fact_order_items (product_key);
