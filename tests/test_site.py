import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sca import site

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "frontend" / "src" / "data" / "data.json"


def test_clean_makes_nan_timestamps_and_numpy_json_safe():
    raw = {
        "a": np.float64("nan"),
        "b": np.int64(3),
        "c": pd.Timestamp("2017-10-02"),
        "d": [np.float64(1.5), float("inf")],
    }
    out = site.clean(raw)
    assert out == {"a": None, "b": 3, "c": "2017-10-02", "d": [1.5, None]}
    json.dumps(out, allow_nan=False)


def test_encode_scores_round_trips_scores_and_labels():
    enc = site.encode_scores(pd.Series([0.0, 0.4567, 1.0, 1.7]), pd.Series([0, 1, 1, 0]))
    assert enc == {"s": [0, 457, 1000, 1000], "y": "0110"}


def test_write_data_writes_json_the_react_app_can_import(tmp_path):
    path = site.write_data({"x": [1, float("nan")]}, tmp_path)
    assert path.name == "data.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"x": [1, None]}


@pytest.mark.skipif(not DATA.exists(), reason="frontend data not built")
def test_committed_frontend_data_has_every_section_and_consistent_scores():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    assert {"results", "monthly", "delivery", "risk", "forecast", "inventory", "packs", "assumptions"} <= set(d)
    assert len(d["risk"]["scores"]["s"]) == len(d["risk"]["scores"]["y"]) == d["risk"]["n_test"]
    for pack in d["packs"]:  # every pack shown must carry the log of how it was produced
        assert pack["validation"]["mode"] in {"llm", "template"} and pack["facts"]
