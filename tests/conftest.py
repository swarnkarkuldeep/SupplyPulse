from pathlib import Path

import pandas as pd
import pytest

from sca import clean as cl
from sca.config import SAMPLE_FILE, load_config

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample" / SAMPLE_FILE


@pytest.fixture(scope="session")
def raw_sample() -> pd.DataFrame:
    return pd.read_csv(SAMPLE_PATH, encoding=load_config().paths.raw_encoding)


@pytest.fixture(scope="session")
def _cleaned(raw_sample):
    flat, log = cl.clean_orders(raw_sample)
    return flat, log, cl.build_star_schema(flat)


@pytest.fixture
def flat(_cleaned) -> pd.DataFrame:
    return _cleaned[0].copy()


@pytest.fixture
def clean_log(_cleaned):
    return _cleaned[1]


@pytest.fixture
def tables(_cleaned) -> dict[str, pd.DataFrame]:
    """Fresh copies per test so broken-fixture tests can mutate freely."""
    return {name: df.copy() for name, df in _cleaned[2].items()}
