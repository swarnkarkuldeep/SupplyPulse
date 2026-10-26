import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sca import site

ROOT = Path(__file__).resolve().parents[1]


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


def test_write_data_is_a_script_that_a_page_can_load_from_disk(tmp_path):
    path = site.write_data({"x": [1, float("nan")]}, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("window.SCA_DATA = ") and text.rstrip().endswith(";")
    assert json.loads(text[len("window.SCA_DATA = ") :].rstrip().rstrip(";")) == {"x": [1, None]}


def test_every_element_the_page_script_looks_up_exists_in_the_html():
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'id="([^"]+)"', html))
    wanted = set(re.findall(r'\$\("#([\w-]+)"\)', js))
    assert wanted - ids == set()
    binds = set(re.findall(r'data-bind="([^"]+)"', html))
    assert set(re.findall(r'bind\("([\w-]+)"', js)) <= binds


@pytest.mark.skipif(not (ROOT / "site" / "data.js").exists(), reason="site data not built")
def test_committed_site_data_has_every_section_and_matches_results():
    text = (ROOT / "site" / "data.js").read_text(encoding="utf-8")
    d = json.loads(text[len("window.SCA_DATA = ") :].rstrip().rstrip(";"))
    assert {"results", "monthly", "delivery", "risk", "forecast", "inventory", "packs", "assumptions"} <= set(d)
    assert len(d["risk"]["scores"]["s"]) == len(d["risk"]["scores"]["y"]) == d["risk"]["n_test"]
    for pack in d["packs"]:  # every pack shown must carry the log of how it was produced
        assert pack["validation"]["mode"] in {"llm", "template"} and pack["facts"]
