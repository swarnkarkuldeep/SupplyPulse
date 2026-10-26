-- Star schema for SQL Server / Azure SQL. Idempotent: safe to run on every load.
-- Statements are separated by a semicolon at the end of a line.

IF OBJECT_ID(N'dbo.dim_category', N'U') IS NULL
CREATE TABLE dbo.dim_category (
    category_key    INT           NOT NULL PRIMARY KEY,
    category_id     INT           NOT NULL,
    category_name   NVARCHAR(100) NOT NULL,
    department_id   INT           NOT NULL,
    department_name NVARCHAR(100) NOT NULL,
    CONSTRAINT uq_dim_category_id UNIQUE (category_id)
);

IF OBJECT_ID(N'dbo.dim_product', N'U') IS NULL
CREATE TABLE dbo.dim_product (
    product_key     INT           NOT NULL PRIMARY KEY,
    product_card_id INT           NOT NULL,
    product_name    NVARCHAR(200) NOT NULL,
    category_key    INT           NOT NULL,
    list_price      DECIMAL(12,2) NOT NULL,
    CONSTRAINT uq_dim_product_card UNIQUE (product_card_id),
    CONSTRAINT fk_dim_product_category FOREIGN KEY (category_key) REFERENCES dbo.dim_category (category_key)
);

IF OBJECT_ID(N'dbo.dim_customer', N'U') IS NULL
CREATE TABLE dbo.dim_customer (
    customer_key INT           NOT NULL PRIMARY KEY,
    customer_id  INT           NOT NULL,
    segment      NVARCHAR(50)  NOT NULL,
    country      NVARCHAR(100) NULL,
    state        NVARCHAR(50)  NULL,
    city         NVARCHAR(100) NULL,
    CONSTRAINT uq_dim_customer_id UNIQUE (customer_id)
);

IF OBJECT_ID(N'dbo.dim_geography', N'U') IS NULL
CREATE TABLE dbo.dim_geography (
    geography_key INT           NOT NULL PRIMARY KEY,
    market        NVARCHAR(50)  NOT NULL,
    region        NVARCHAR(100) NOT NULL,
    country       NVARCHAR(100) NOT NULL,
    CONSTRAINT uq_dim_geography UNIQUE (market, region, country)
);

IF OBJECT_ID(N'dbo.dim_shipping_mode', N'U') IS NULL
CREATE TABLE dbo.dim_shipping_mode (
    shipping_mode_key INT          NOT NULL PRIMARY KEY,
    shipping_mode     NVARCHAR(50) NOT NULL,
    scheduled_days    INT          NOT NULL,
    CONSTRAINT uq_dim_shipping_mode UNIQUE (shipping_mode)
);

IF OBJECT_ID(N'dbo.dim_date', N'U') IS NULL
CREATE TABLE dbo.dim_date (
    date_key    INT          NOT NULL PRIMARY KEY,
    [date]      DATE         NOT NULL,
    [year]      INT          NOT NULL,
    [quarter]   INT          NOT NULL,
    [month]     INT          NOT NULL,
    month_name  NVARCHAR(20) NOT NULL,
    year_month  CHAR(7)      NOT NULL,
    week_start  DATE         NOT NULL,
    iso_week    INT          NOT NULL,
    day_of_week INT          NOT NULL,
    day_name    NVARCHAR(20) NOT NULL,
    is_weekend  TINYINT      NOT NULL,
    CONSTRAINT uq_dim_date_date UNIQUE ([date])
);

IF OBJECT_ID(N'dbo.fact_order_items', N'U') IS NULL
CREATE TABLE dbo.fact_order_items (
    order_item_id           INT           NOT NULL PRIMARY KEY,
    order_id                INT           NOT NULL,
    order_ts                DATETIME2(0)  NOT NULL,
    ship_ts                 DATETIME2(0)  NOT NULL,
    order_date_key          INT           NOT NULL,
    ship_date_key           INT           NOT NULL,
    order_week              DATE          NOT NULL,
    order_month             DATE          NOT NULL,
    customer_key            INT           NOT NULL,
    product_key             INT           NOT NULL,
    category_key            INT           NOT NULL,
    geography_key           INT           NOT NULL,
    shipping_mode_key       INT           NOT NULL,
    payment_type            NVARCHAR(20)  NOT NULL,
    order_status            NVARCHAR(30)  NOT NULL,
    delivery_status         NVARCHAR(30)  NOT NULL,
    quantity                INT           NOT NULL,
    unit_price              DECIMAL(12,2) NOT NULL,
    discount_amount         DECIMAL(12,2) NOT NULL,
    discount_rate           DECIMAL(6,4)  NOT NULL,
    gross_sales             DECIMAL(12,2) NOT NULL,
    net_sales               DECIMAL(12,2) NOT NULL,
    profit                  DECIMAL(12,2) NOT NULL,
    profit_ratio            DECIMAL(8,4)  NOT NULL,
    cost_amount             DECIMAL(12,2) NOT NULL,
    profit_per_unit         DECIMAL(12,2) NOT NULL,
    shipping_days_real      INT           NOT NULL,
    shipping_days_scheduled INT           NOT NULL,
    shipping_delay_days     INT           NOT NULL,
    late_delivery_risk      TINYINT       NOT NULL,
    is_late                 TINYINT       NOT NULL,
    is_valid_order          TINYINT       NOT NULL,
    CONSTRAINT fk_fact_customer  FOREIGN KEY (customer_key)      REFERENCES dbo.dim_customer (customer_key),
    CONSTRAINT fk_fact_product   FOREIGN KEY (product_key)       REFERENCES dbo.dim_product (product_key),
    CONSTRAINT fk_fact_category  FOREIGN KEY (category_key)      REFERENCES dbo.dim_category (category_key),
    CONSTRAINT fk_fact_geography FOREIGN KEY (geography_key)     REFERENCES dbo.dim_geography (geography_key),
    CONSTRAINT fk_fact_shipmode  FOREIGN KEY (shipping_mode_key) REFERENCES dbo.dim_shipping_mode (shipping_mode_key),
    CONSTRAINT fk_fact_orderdate FOREIGN KEY (order_date_key)    REFERENCES dbo.dim_date (date_key),
    CONSTRAINT fk_fact_shipdate  FOREIGN KEY (ship_date_key)     REFERENCES dbo.dim_date (date_key)
);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_fact_order_id' AND object_id = OBJECT_ID(N'dbo.fact_order_items'))
CREATE INDEX ix_fact_order_id ON dbo.fact_order_items (order_id);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_fact_order_week_category' AND object_id = OBJECT_ID(N'dbo.fact_order_items'))
CREATE INDEX ix_fact_order_week_category ON dbo.fact_order_items (order_week, category_key) INCLUDE (quantity, net_sales, is_valid_order);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_fact_order_month' AND object_id = OBJECT_ID(N'dbo.fact_order_items'))
CREATE INDEX ix_fact_order_month ON dbo.fact_order_items (order_month) INCLUDE (net_sales, profit, is_late, is_valid_order);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_fact_geography' AND object_id = OBJECT_ID(N'dbo.fact_order_items'))
CREATE INDEX ix_fact_geography ON dbo.fact_order_items (geography_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_fact_shipping_mode' AND object_id = OBJECT_ID(N'dbo.fact_order_items'))
CREATE INDEX ix_fact_shipping_mode ON dbo.fact_order_items (shipping_mode_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_fact_customer' AND object_id = OBJECT_ID(N'dbo.fact_order_items'))
CREATE INDEX ix_fact_customer ON dbo.fact_order_items (customer_key);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'ix_fact_product' AND object_id = OBJECT_ID(N'dbo.fact_order_items'))
CREATE INDEX ix_fact_product ON dbo.fact_order_items (product_key);
