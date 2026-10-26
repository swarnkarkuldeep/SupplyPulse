# PROJECT SPEC: Supply Chain Analytics & Demand Forecasting

> **How to use this file:** create an empty folder (suggested repo name: `supply-chain-analytics`), put this file in it as `PROJECT_SPEC.md`, open Claude Code there and say:
> *"Read PROJECT_SPEC.md fully. Ask me any clarifying questions, then propose your plan for Phase 0 and wait for my go-ahead."*

---

## 1. Who I am and what this project is for

I'm Kuldeep, a final-year B.Tech CSE student. I'm building this as a portfolio project for **data / operations analytics internships**, specifically roles like Philips' *Opex Analytical Intern*. Those roles ask for:

- data cleaning, data structures for analytics, and data quality
- visual reporting through dashboards, scorecards and review packs
- statistical and ML models: forecasting, regression and simulation
- supply chain and finance domain thinking
- AI-powered insight tools, with GenAI and agentic AI as a plus

The finished repo should read like work from an analyst on a real operations team. That means business questions first, a clean and reproducible pipeline, honest validated results, and a dashboard plus written review a manager could act on.

---

## 2. Ground rules (follow these throughout)

1. **Work phase by phase.** At the end of every phase:
   - run lint and tests
   - summarize what you built and the key numbers
   - make a git commit with a clear message
   - **stop and wait for my review** before starting the next phase
2. **Never invent results.** Every number in the README, `RESULTS.md` or any report must come from code that actually ran in this repo. If something underperforms or fails, say so plainly. Don't write "illustrative" numbers anywhere.
3. **Inspect the data before trusting this spec.** The column names and quirks below come from the dataset's public description. Verify them by profiling and adapt if reality differs, telling me what changed.
4. **Logic lives in `src/`** as importable, tested modules. Notebooks only tell the story and call functions from `src/`.
5. **Reproducibility:**
   - fixed random seeds
   - pinned dependencies
   - one config file
   - one CLI command that runs the whole pipeline end to end
6. **Cross-platform, Windows-first.** I'll build the dashboard in Power BI Desktop, which is Windows-only. Use a Python CLI (Typer) instead of Makefiles or bash-only scripts.
7. **Never commit** raw data, secrets, `.env`, or large generated files.
8. **Ask before adding** any heavy dependency not listed in section 5.
9. **Don't over-engineer.** No Airflow, Spark, Kubernetes or microservices. This is a clean analytics repo.

---

## 3. Business framing (put this in the README)

**Scenario:** I'm an analyst on the Operations Excellence team at *DataCo*, a global retailer. Leadership wants a monthly operations review that answers:

| # | Business question | Method |
|---|---|---|
| Q1 | How much demand should we expect per product category over the next 8–12 weeks? | Time-series forecasting |
| Q2 | Which orders are likely to ship late, and what drives lateness? | Classification + SHAP |
| Q3 | How much safety stock do key categories need to keep stockout risk low, and what does it cost? | Monte Carlo simulation |
| Q4 | Where are we losing margin (discounts, categories, regions)? | Profitability analysis + regression |
| Q5 | Can the monthly review be drafted automatically without making up numbers? | Grounded LLM review pack |

---

## 4. Dataset

**Source:** Kaggle, *"DataCo SMART SUPPLY CHAIN FOR BIG DATA ANALYSIS"*. Search that title on Kaggle.

- **Main file:** `DataCoSupplyChainDataset.csv`, about 180K order-item rows and about 50 columns.
- **Data dictionary:** `DescriptionDataCoSupplyChain.csv`.
- **Ignore:** `tokenized_access_logs.csv` (not needed).

**Placement:** I'll download the files manually into `data/raw/`.

- Add download instructions to the README.
- Add an optional `scripts/download_data.py` that uses the Kaggle CLI if credentials exist.
- `data/raw/` and `data/processed/` are git-ignored.
- Create a small committed **`data/sample/`** of about 2–3K rows, stratified by market and shipping mode, for tests and CI.

**Known quirks to verify and handle:**

- **Encoding.** The file is reportedly **latin-1 / ISO-8859-1**, not UTF-8.
- **PII.** Masked PII columns (customer email, password) and personal fields (first/last name, street) are not needed. Drop them.
- **Dates.** `order date (DateOrders)` and `shipping date (DateOrders)` are strings like `1/31/2018 22:56`. Parse them with an explicit format.
- **Redundant column pairs.** Likely examples:
  - `Sales` vs `Order Item Total`
  - `Customer Id` vs `Order Customer Id`
  - `Product Card Id` vs `Order Item Cardprod Id`
  - `Category Id` vs `Product Category Id`
  - `Benefit per order` vs `Order Profit Per Order`

  Confirm each pair is truly redundant before dropping one side.
- **Mostly-empty or useless columns.** `Product Description`, `Product Image` and `Order Zipcode` are likely examples. Check null rates and drop with a logged reason.
- **Columns to confirm.** `Type` appears to be payment type (DEBIT / TRANSFER / CASH / PAYMENT). Confirm it.
- **Order Status.** It includes values like `CANCELED` and `SUSPECTED_FRAUD`. Decide and document how these are treated in demand, delivery and margin analyses.
- **Tail periods.** Volume may drop sharply or change pattern in the final months. Plot monthly order counts, detect incomplete or abnormal tail periods, and **truncate them for forecasting**. Document the cutoff date and why.

---

## 5. Tech stack

**Language:** Python 3.11.

**Core libraries:**

| Purpose | Libraries |
|---|---|
| Data | pandas, numpy, pyarrow |
| Database | SQLAlchemy 2.x, pyodbc |
| Statistics and forecasting | statsmodels (OLS, SARIMAX), prophet |
| Machine learning | scikit-learn, lightgbm, shap |
| Charts | matplotlib (plotly optional) |
| CLI | typer |
| Config | pydantic-settings, python-dotenv, PyYAML |
| LLM | google-genai (Gemini), groq |
| Quality | pytest, ruff |

**Databases:**

- **Primary:** SQL Server 2022 in Docker. Use image `mcr.microsoft.com/mssql/server:2022-latest` with `ACCEPT_EULA=Y` and `MSSQL_PID=Developer`, and take the SA password from `.env`. Add a healthcheck and a named volume.
- **Azure SQL:** the same code must work against Azure SQL just by changing the connection string in `.env`.
- **Fallback:** SQLite for tests, CI, and running without SQL Server.
  - Keep SQL as portable as possible.
  - Where T-SQL and SQLite differ (date functions, `TOP` vs `LIMIT`), isolate dialect-specific files under `sql/sqlserver/` and `sql/sqlite/`.
- **Windows connection notes:** pyodbc needs Microsoft's **ODBC Driver 18 for SQL Server**, and local Docker needs `TrustServerCertificate=yes`. Document both in the README.

**Install fallbacks:** if `prophet` or `lightgbm` won't install cleanly, tell me and fall back to SARIMA-only or scikit-learn's `HistGradientBoosting*` respectively. Don't silently skip them.

---

## 6. Repo structure (target)

```
supply-chain-analytics/
├── README.md                  # written like a business report (see Phase 8)
├── PROJECT_SPEC.md            # this file
├── pyproject.toml / requirements.txt (pinned)
├── .env.example               # DB connection, LLM keys, model names. No real secrets
├── .gitignore
├── config.yaml                # all tunable parameters (top-N, horizons, sim assumptions, seeds)
├── docker-compose.yml         # SQL Server
├── .github/workflows/ci.yml   # ruff + pytest on SQLite + data/sample, LLM in no-llm mode
├── data/
│   ├── raw/                   # git-ignored
│   ├── processed/             # git-ignored
│   └── sample/                # small committed sample for tests/CI
├── sql/
│   ├── sqlserver/  schema.sql, views/*.sql, kpi_queries/*.sql
│   └── sqlite/     (only what differs)
├── src/sca/
│   ├── config.py   db.py   cli.py
│   ├── ingest.py   clean.py   quality.py   load.py
│   ├── eda.py   profitability.py
│   ├── forecasting.py   risk_model.py   simulation.py
│   ├── kpis.py   review_pack.py   grounding.py
│   └── viz.py                 # shared chart style
├── notebooks/  01_eda.ipynb  02_forecasting.ipynb  03_delivery_risk.ipynb  04_simulation.ipynb
├── dashboard/  theme.json  dax_measures.md  dashboard_spec.md  BUILD_GUIDE.md  data/  screenshots/
├── reports/    data_profile.md  cleaning_log.md  data_quality_report.md  eda_findings.md
│               forecast_results.md  risk_model_results.md  simulation_results.md
│               review_packs/  figures/  RESULTS.md
└── tests/
```

**CLI commands** (`python -m sca <command>`):

- `ingest`, `quality`, `load`, `eda`, `forecast`, `risk`, `simulate`, `kpis`, `review-pack`
- `all`, which runs everything in order
- `--sample` flag on every command to run on `data/sample/`

---

## 7. Phases

### Phase 0: Scaffold (no data needed)

- Create the repo structure, pinned dependencies, `.gitignore`, `.env.example`, `config.yaml` and `docker-compose.yml`.
- Write `db.py` with an SQLAlchemy engine factory that switches between SQL Server, Azure SQL and SQLite from `.env`.
- Build the CLI skeleton with all commands stubbed.
- Configure ruff and pytest, and add a GitHub Actions CI workflow.
- Write a README skeleton with the section headings from Phase 8.
- **Stop.**

### Phase 1: Profiling, cleaning, data quality and loading

**1. Profile the raw data.** Report:

- shape, dtypes, null rates and cardinality
- duplicate rows
- date range and monthly order volume (with a chart)
- value distributions of key numeric columns

Output: `reports/data_profile.md` plus figures.

**2. Clean the data.**

- Use snake_case column names and explicit dtypes.
- Parse dates.
- Trim and standardize categoricals.
- Drop PII, redundant and useless columns. Log every dropped column with its reason in `reports/cleaning_log.md`.
- Derive analysis fields: `order_week`, `order_month`, `shipping_delay_days` (real − scheduled), `is_late`, and margin fields.
- Keep raw → clean row counts and log every row filtered out with the reason.

**3. Model the data as a star schema.**

- **Fact table:** `fact_order_items`, with grain of one order item.
- **Dimensions:** `dim_product`, `dim_category` (with department), `dim_customer` (segment, country, state, city only, no PII), `dim_geography` (market, region, country), `dim_shipping_mode`, `dim_date` (full calendar table, marked for Power BI).
- Use surrogate keys, primary keys, foreign keys and sensible indexes.

**4. Write data-quality checks as code** in `quality.py`. Each check has a name, description, severity (`error` / `warn`), failing-row count and sample failing keys. Include at least:

- primary-key uniqueness for every table
- not-null on critical columns
- foreign-key referential integrity from fact to every dimension
- valid ranges: quantity > 0, discount rate between 0 and 1, prices ≥ 0
- date logic: ship date ≥ order date
- reconciliation: sales ≈ price × quantity − discount, within a tolerance
- label consistency: `late_delivery_risk` == (actual shipping days > scheduled)
- no duplicate order items

Output both `reports/data_quality_report.md` and a JSON version. The pipeline **fails on any `error`-severity failure**.

**5. Load to the database** with SQLAlchemy.

- Use `fast_executemany` for pyodbc.
- Make loads idempotent with truncate-and-load.
- Verify loaded row counts match the cleaned data.

**6. Create SQL views** in `sql/sqlserver/views/`. Use CTEs and window functions where natural (`LAG` for month-on-month change, `RANK` for top categories); this showcases real SQL.

| View | Grain | Measures |
|---|---|---|
| `vw_weekly_demand` | category × week | units, sales |
| `vw_delivery_performance` | shipping mode × region × month | orders, late %, average delay |
| `vw_margin_analysis` | category × region × month | sales, profit, margin %, average discount |
| `vw_kpi_monthly` | month | revenue, profit, margin %, on-time %, orders, average order value, MoM change |

**7. Tests.**

- cleaning functions
- each quality check against deliberately broken fixtures, confirming it catches the problem
- the load round-trip on SQLite

**Stop.**

### Phase 2: EDA and profitability (finance angle)

- Write `notebooks/01_eda.ipynb` using `src/` functions. Cover:
  - demand trend and seasonality by category
  - delivery performance by mode and region
  - margin by category and region
  - discount vs profit
- **Regression:** run an OLS model (statsmodels) of item profit ratio on discount rate, controlling for category, region and shipping mode.
  - Interpret coefficients in business language (e.g., "each +1 pp of discount is associated with −x pp of margin").
  - Check residuals and assumptions, and use robust standard errors if needed.
  - State clearly that this is associational, not causal.
- Output `reports/eda_findings.md` with **5–8 findings**. Each finding gets a number, a chart and a "so what" sentence.
- Use one consistent, clean chart style through `viz.py`. Every chart title states the insight, not just the variable names.
- **Stop.**

### Phase 3: Demand forecasting (Q1)

**Target:** weekly units sold per category.

- Select the **top N categories** by volume, choosing N so every series has enough history and few zero weeks. Justify the choice.
- Also forecast total units.
- Fill missing weeks explicitly with zero and apply the tail truncation from section 4.

**Models:**

1. Seasonal-naive (the baseline to beat)
2. Moving average
3. SARIMA (SARIMAX, small AIC-based grid)
4. Prophet
5. LightGBM global model with lag, rolling and calendar features. Every feature must be computed **strictly from the past**. Choose recursive or direct multi-step forecasting and justify it.

**Validation:** rolling-origin backtesting, about 4–6 folds with an 8-week horizon. **Never use a random split.**

**Metrics:**

- **WAPE** (primary)
- MAPE (report it, but flag series where low actuals make it unstable)
- MAE and bias

Report per category and aggregated, plus **% improvement over seasonal-naive**.

**Final step:**

- Pick a champion model, per category or overall, with reasoning.
- Produce a 12-week forecast with prediction intervals. Use native intervals for SARIMA and Prophet, and backtest residual quantiles for LightGBM.
- Save backtest residuals per category; Phase 5 needs them.

**Outputs:**

- `reports/forecast_results.md`
- forecast charts
- `fct_forecast` table in the database (actuals + forecast + intervals, for Power BI)

**Stop.**

### Phase 4: Late-delivery risk model (Q2)

**Target:** `late_delivery_risk`.

**Model at order level, not item level.** Items in one order share the same label, so item-level rows would leak across splits. Aggregate items into order-level features such as number of items, total quantity, total sales, dominant category and max discount.

**Target leakage is the #1 risk.** Exclude everything known only after shipping or delivery:

- actual shipping days
- delivery status
- shipping date
- order status (verify)
- any field derived from these

Add a **unit test asserting forbidden columns never reach the feature matrix**.

**Allowed features** are those known at order time, for example:

- shipping mode and scheduled shipping days
- market, region and country (group rare levels or encode inside CV only)
- customer segment, category and department
- price, quantity and discount
- payment type
- order day-of-week, hour and month

**Split:** time-based, training on earlier orders and testing on the most recent ~20%.

**Models:** a logistic regression baseline and LightGBM.

**Metrics:**

- ROC-AUC and PR-AUC
- precision and recall at a chosen threshold
- confusion matrix
- calibration plot

Choose the threshold using a simple, documented cost assumption.

**Sanity check:** if ROC-AUC looks suspiciously high (> 0.95), **investigate leakage before celebrating**. If lateness turns out to be largely explained by shipping mode and scheduled days, report that honestly as a business finding.

**Explainability:**

- SHAP summary plot plus dependence plots for the top drivers
- a plain-English driver table, such as late % by shipping mode and region

**Outputs:**

- `reports/risk_model_results.md`
- `fct_late_risk_scores` in the database
- SHAP driver export for Power BI

**Stop.**

### Phase 5: Inventory Monte Carlo simulation (Q3)

The dataset has **no inventory data**, so this simulates an inventory policy. Every assumption goes in `config.yaml` and is documented in `reports/simulation_results.md`. Assumptions to set:

- supplier lead-time distribution (e.g., 1–3 weeks; **not** the customer shipping days)
- review period
- unit cost proxy
- holding cost as % of unit cost per week
- target service levels

**Policy:** periodic-review order-up-to (R, S), where S = forecast over (R + L) + safety stock.

1. Compute the analytic baseline: safety stock = z · σ(forecast error) · √(R + L).
2. Simulate demand as the Phase 3 forecast plus **bootstrapped backtest residuals**, with lead time sampled from its distribution.
3. Run **10,000 simulations** over a 52-week horizon for each safety-stock level on a grid. Use vectorized numpy and a fixed seed.

**Metrics per safety-stock level:**

- probability of at least one stockout
- cycle service level and fill rate
- average inventory and holding cost

**Outputs:**

- a trade-off curve of stockout risk vs holding cost
- a results table
- a one-sentence recommendation per category, in the form: *"Raising safety stock from X to Y units cuts stockout risk from A% to B% for C% more holding cost."*
- results written to `fct_simulation_results` for Power BI

**Stop.**

### Phase 6: KPI layer and Power BI assets

You can't build the `.pbix` file. Prepare everything so I can build the dashboard myself in about a day.

**1. Final model in SQL Server.** The star schema plus `fct_forecast`, `fct_late_risk_scores`, `fct_simulation_results` and a SHAP driver table. Also export CSV/Parquet copies to `dashboard/data/` as an import-mode fallback.

**2. `dashboard/dax_measures.md`.** Every measure with DAX code and a one-line explanation, including:

- Total Revenue, Total Profit, Margin %
- Orders, Average Order Value
- On-Time Delivery %, Late Orders, Average Delay Days
- Forecast vs Actual, Forecast WAPE
- MoM % and YoY % (time intelligence on the marked date table)

**3. `dashboard/theme.json`.** A Power BI report theme that is clean, professional and accessible (colorblind-safe palette), consistent with the README chart style.

**4. `dashboard/dashboard_spec.md`.** A page-by-page spec. For each visual, give the type, fields and measures, filters, approximate position, and a **title that states the insight**.

| Page | Contents |
|---|---|
| 1. Executive Scorecard | KPI cards with MoM deltas, revenue and margin trend, on-time % trend, top/bottom categories, slicers for market, region and date |
| 2. Demand Forecast | Actual vs forecast with intervals, category slicer, accuracy table |
| 3. Delivery Risk | Late % heatmap (shipping mode × region), top-drivers bar from SHAP, risk-scored recent orders table |
| 4. Margin & Discounts (optional) | Discount vs margin, loss-making category × region combinations |

**5. `dashboard/BUILD_GUIDE.md`.** Step-by-step Power BI Desktop instructions:

1. Connect to SQL Server (`localhost,1433`).
2. Set up relationships.
3. Mark the date table.
4. Import the theme.
5. Create the measures.
6. Build each page.
7. Export screenshots to `dashboard/screenshots/` and a PDF of the report.

**6. Static PNG charts.** Python-generated versions of the key dashboard views, so the README works for readers without Power BI.

**Stop.**

### Phase 7: GenAI monthly review pack (Q5, grounded)

**1. `kpis.py`.** Runs a fixed, versioned set of SQL queries for a chosen month and writes `facts.json`. Each fact has:

- `id`
- metric name
- value and unit
- period
- comparison value and delta
- source query name

**2. `review_pack.py`.** Sends the facts, plus top drivers from Phases 2–5, to the LLM with a strict system prompt.

- The output is a 1-page operations review with these sections: headline; what changed; why (drivers); risks; recommended actions with owners.
- **Use only numbers present in the facts**, and cite fact ids inline like `[F3]`.

**3. `grounding.py` validator.**

- Extract every number in the LLM output. Each must match a fact value within rounding tolerance, or be an allowed date or ordinal.
- Every cited fact id must exist.
- On failure, retry once with feedback listing the offending numbers.
- If it still fails, **fall back to a deterministic template report**.
- Log validation results.

**4. Providers.**

- Gemini is primary, with Groq as fallback.
- **Model names come from `.env`.** Don't hardcode model versions.
- Add a `--no-llm` deterministic template mode for CI and for running without API keys.

**5. Outputs.**

- `reports/review_packs/review_YYYY-MM.md`, with optional HTML/PDF export
- one real generated sample pack committed to the repo

**6. Tests.** Use fake LLM outputs containing fabricated numbers and confirm the validator rejects them. Confirm the full pipeline runs in `--no-llm` mode.

**Optional stretch (only if I ask):** a read-only natural-language Q&A agent.

- text-to-SQL over **whitelisted views only**
- SELECT-only enforced by parsing with `sqlglot`
- row limits
- a read-only database user

**Stop.**

### Phase 8: Results, README and polish

**1. `reports/RESULTS.md`.** One table of every number I might put on my resume, with "how computed" and "source file" columns:

- raw → clean row counts
- number of data-quality checks (and how many error vs warn)
- top-N categories chosen
- champion forecast model, WAPE and MAPE, and % improvement over seasonal-naive
- late-risk ROC-AUC and PR-AUC
- simulated stockout risk before and after, plus holding cost change
- number of DAX measures
- number of tests

Also recommend whether I should cite MAPE or WAPE, and why.

**2. README written as a business report,** in this order:

1. Title and one-line pitch
2. **Executive summary** (3–5 findings with numbers)
3. Business questions → answers
4. Dashboard screenshots
5. Pipeline diagram (Mermaid)
6. Methods and validation (backtesting, leakage prevention, data-quality gates, LLM grounding)
7. **Limitations and assumptions** (honest: synthetic-looking dataset, simulated inventory, associational regression)
8. How to run: Docker SQL Server, `.env`, CLI commands, SQLite-only mode
9. Repo structure and tech stack

**3. Quality pass.**

- ruff clean
- type hints and docstrings on public functions
- all tests green and CI green
- notebooks re-run top to bottom without errors

**4. Final message to me:** print the RESULTS.md table so I can update my resume placeholders.

---

## 8. Definition of done

- [ ] `python -m sca all` runs end to end on the full data. `python -m sca all --sample` runs in CI with no SQL Server and no API keys.
- [ ] Data-quality gate blocks the pipeline on error-severity failures.
- [ ] No random splits anywhere. Forecasting uses rolling-origin backtests; the risk model uses a time-based split at order level.
- [ ] A leakage test exists and passes.
- [ ] The forecast beats seasonal-naive, or the README says honestly where it doesn't.
- [ ] Simulation assumptions are documented and configurable.
- [ ] The LLM review pack passes the grounding validator, and the fabricated-number tests pass.
- [ ] Power BI assets are complete: DAX, theme, spec and build guide.
- [ ] README reads as a business report, with real numbers and screenshots.
- [ ] `RESULTS.md` is complete.

## 9. Things to avoid

- Random train/test splits on time-ordered data
- Any feature not known at order time in the risk model
- Hardcoded paths, credentials or model names
- Business logic that lives only in notebooks
- Fabricated, placeholder or "example" numbers in reports
- Charts without units or with titles that don't state the insight
- Scope creep beyond this spec without asking me first
