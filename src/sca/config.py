"""Configuration: tunable parameters from config.yaml, connection details from .env."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_FILE = "sample_orders.csv"


class Env(BaseSettings):
    """Secrets and connection settings, read from the environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_backend: Literal["sqlserver", "azure", "sqlite"] = "sqlite"
    sqlite_path: str = "data/processed/sca.db"
    db_host: str = "localhost"
    db_port: int = 1433
    db_name: str = "supplypulse"
    db_user: str = "sa"
    db_password: str = ""
    odbc_driver: str = "ODBC Driver 18 for SQL Server"
    trust_server_certificate: Literal["yes", "no"] = "yes"
    database_url: str = ""

    gemini_api_key: str = ""
    gemini_model: str = ""
    groq_api_key: str = ""
    groq_model: str = ""


class PathsCfg(BaseModel):
    raw_dir: str = "data/raw"
    processed_dir: str = "data/processed"
    sample_dir: str = "data/sample"
    reports_dir: str = "reports"
    raw_file: str = "DataCoSupplyChainDataset.csv"
    raw_encoding: str = "latin-1"


class SampleCfg(BaseModel):
    rows: int = 2500
    stratify_by: list[str] = Field(default_factory=lambda: ["market", "shipping_mode"])


class ForecastCfg(BaseModel):
    top_n_categories: int = 10
    horizon_weeks: int = 8
    final_horizon_weeks: int = 12
    backtest_folds: int = 5
    seasonal_period: int = 52
    interval_level: float = 0.8
    # Abnormal-tail detection (section 4 of the spec): a week is abnormal when it is below
    # drop_ratio x the median of the previous baseline_weeks and all later weeks are too.
    tail_baseline_weeks: int = 26
    tail_drop_ratio: float = 0.6
    cutoff_override: str | None = None  # "YYYY-MM-DD" to force the last usable date
    # Phase 3 settings
    models: list[str] = Field(
        default_factory=lambda: ["seasonal_naive", "moving_average", "sarima", "prophet", "lightgbm"]
    )
    sample_models: list[str] = Field(default_factory=lambda: ["seasonal_naive", "moving_average", "lightgbm"])
    sample_folds: int = 2
    min_history_weeks: int = 100  # a series needs this many weeks before the first backtest origin
    max_zero_week_share: float = 0.05  # a series with more zero weeks than this is too sparse to forecast
    moving_average_window: int = 8
    sarima_orders: list[list[int]] = Field(
        default_factory=lambda: [[0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 1, 1], [1, 1, 1], [2, 1, 0]]
    )
    sarima_fourier_k: list[int] = Field(default_factory=lambda: [0, 2])
    lgbm_lags: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 8, 13])
    lgbm_params: dict = Field(
        default_factory=lambda: {
            "n_estimators": 300,
            "learning_rate": 0.05,
            "num_leaves": 15,
            "min_child_samples": 20,
            "subsample": 0.8,
            "subsample_freq": 1,
            "colsample_bytree": 0.8,
        }
    )
    n_jobs: int = 1


class RiskCfg(BaseModel):
    test_fraction: float = 0.2
    cost_false_negative: float = 5.0
    cost_false_positive: float = 1.0


class SimulationCfg(BaseModel):
    n_sims: int = 10_000
    horizon_weeks: int = 52
    review_period_weeks: int = 1
    lead_time_weeks: list[int] = Field(default_factory=lambda: [1, 2, 3])
    lead_time_probs: list[float] = Field(default_factory=lambda: [0.3, 0.5, 0.2])
    holding_cost_pct_per_week: float = 0.005
    unit_cost_proxy_pct_of_price: float = 0.6
    service_levels: list[float] = Field(default_factory=lambda: [0.90, 0.95, 0.98, 0.99])


class ReviewPackCfg(BaseModel):
    top_drivers: int = 5


class Config(BaseModel):
    """Typed view of config.yaml."""

    seed: int = 42
    paths: PathsCfg = Field(default_factory=PathsCfg)
    sample: SampleCfg = Field(default_factory=SampleCfg)
    forecast: ForecastCfg = Field(default_factory=ForecastCfg)
    risk: RiskCfg = Field(default_factory=RiskCfg)
    simulation: SimulationCfg = Field(default_factory=SimulationCfg)
    review_pack: ReviewPackCfg = Field(default_factory=ReviewPackCfg)

    def resolve(self, relative: str) -> Path:
        """Resolve a project-relative path against the repo root."""
        return PROJECT_ROOT / relative


@dataclass(frozen=True)
class RunPaths:
    """Where one pipeline run reads and writes. Sample runs never touch full-data outputs."""

    raw_file: Path
    processed_dir: Path
    reports_dir: Path

    @property
    def figures_dir(self) -> Path:
        return self.reports_dir / "figures"


def run_paths(cfg: Config, sample: bool = False) -> RunPaths:
    """Resolve input/output locations for a full or --sample run."""
    if sample:
        processed = cfg.resolve(cfg.paths.processed_dir) / "sample"
        return RunPaths(
            raw_file=cfg.resolve(cfg.paths.sample_dir) / SAMPLE_FILE,
            processed_dir=processed,
            reports_dir=processed / "reports",
        )
    return RunPaths(
        raw_file=cfg.resolve(cfg.paths.raw_dir) / cfg.paths.raw_file,
        processed_dir=cfg.resolve(cfg.paths.processed_dir),
        reports_dir=cfg.resolve(cfg.paths.reports_dir),
    )


def load_config(path: str | Path | None = None) -> Config:
    """Load config.yaml (default: repo root) into a validated Config."""
    cfg_path = Path(path) if path else PROJECT_ROOT / "config.yaml"
    with open(cfg_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config(**data)


@lru_cache
def get_env() -> Env:
    """Return the cached environment settings."""
    return Env(_env_file=PROJECT_ROOT / ".env")
