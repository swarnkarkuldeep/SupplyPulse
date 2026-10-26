// The pipeline's outputs, written by `python -m sca site`. Nothing on the page is typed in by hand.
import raw from "./data/data.json";

export interface Results {
  rows_raw: number;
  rows_clean: number;
  orders: number;
  revenue: number;
  profit: number;
  margin: number;
  on_time: number;
  excluded_share: number;
  cutoff: string;
  tail_drop_pct: number;
  dq_checks: number;
  dq_failing_errors: number;
  dq_failing_warnings: number;
  tests: number;
  dax_measures: number;
  n_categories: number;
  folds: number;
  horizon_weeks?: number;
  wape: number;
  wape_ma: number;
  wape_improvement: number;
  roc_auc: number;
  roc_auc_mode_only: number;
  risk_champion: string;
  late_first_class: number;
  textbook_service_95: number;
  loss_items_share: number;
  loss_vs_gross_profit: number;
  loss_top10_products: number;
  discount_r2: number;
}

export interface MonthRow {
  month: string;
  orders: number;
  revenue: number;
  profit: number;
  margin_pct: number;
  on_time_pct: number;
}

export interface ModeRow {
  shipping_mode: string;
  scheduled_days: number;
  late: number;
  orders: number;
}

export interface HourJump {
  shipping_mode: string;
  late_before: number;
  late_after: number;
  orders_before: number;
  orders_after: number;
}

export interface RiskMetrics {
  roc_auc: number;
  threshold: number;
}

export interface Risk {
  champion: string;
  metrics: Record<string, RiskMetrics>;
  drivers: { feature: string; share: number }[];
  scores: { s: number[]; y: string };
  n_test: number;
}

export interface CategoryForecast {
  history: [string, number][];
  forecast: [string, number, number, number][];
  backtest: [string, number, number][];
  wape: number | null;
}

export interface Forecast {
  champion: string;
  cutoff: string;
  folds: number;
  horizon_weeks: number;
  models: { model: string; wape: number; mape: number }[];
  categories: Record<string, CategoryForecast>;
}

export interface GridRow {
  basis: "textbook" | "lead_time_aware";
  z: number;
  safety_stock: number;
  analytic_service_target: number | null;
  p_any_stockout: number;
  cycle_service_level: number;
  holding_cost: number;
}

export interface Fact {
  id: string;
  metric: string;
  value: number | string;
  unit?: string | null;
  period: string;
  comparison_value?: number | null;
  comparison_period?: string | null;
  delta?: number | null;
  delta_unit?: string | null;
  source_query: string;
}

export interface Attempt {
  provider: string | null;
  ok: boolean;
  numbers_checked: number;
  offending_numbers: string[];
  error: string | null;
}

export interface Pack {
  period: string;
  markdown: string;
  facts: Fact[];
  query_checksum: string;
  validation: { mode: "llm" | "template"; provider: string | null; reason: string; attempts: Attempt[] };
}

export interface SupplyPulseData {
  assumptions: {
    paths: number;
    lead_time_weeks: number[];
    lead_time_probs: number[];
    holding_cost_pct_per_week: number;
    interval_level: number;
  };
  results: Results;
  monthly: MonthRow[];
  delivery: { by_mode: ModeRow[]; hour_jump: HourJump[]; late_rate: number; orders: number };
  risk: Risk;
  forecast: Forecast;
  inventory: Record<string, { grid: GridRow[] }>;
  packs: Pack[];
}

export const data = raw as unknown as SupplyPulseData;
