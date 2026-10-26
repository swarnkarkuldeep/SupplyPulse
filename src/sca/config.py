"""Configuration: tunable parameters from config.yaml, connection details from .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
