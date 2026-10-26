import json
import re

import pytest
from typer.testing import CliRunner

from sca import kpis, load, review_pack
from sca.cli import app
from sca.config import ConfigError, Env
from sca.db import get_engine
from sca.grounding import validate

runner = CliRunner()

FACTS = {
    "version": "1",
    "period": "2018-01",
    "comparison_period": "2017-12",
    "query_checksum": "abc123",
    "unavailable_queries": [],
    "facts": [
        {"id": "F1", "metric": "Revenue", "value": 284672.01, "unit": "USD", "period": "2018-01",
         "comparison_value": 432004.27, "comparison_period": "2017-12", "delta": -34.1, "delta_unit": "%",
         "source_query": "q01_kpi_month"},
        {"id": "F2", "metric": "Revenue versus the trailing-year monthly average", "value": 284672.01, "unit": "USD",
         "period": "2018-01", "comparison_value": 845033.42, "comparison_period": "average of 12 months to 2017-12",
         "delta": -66.31, "delta_unit": "%", "source_query": "q02_kpi_baseline"},
        {"id": "F3", "metric": "Margin", "value": 11.37, "unit": "%", "period": "2018-01", "comparison_value": 15.05,
         "comparison_period": "2017-12", "delta": -3.68, "delta_unit": "pp", "source_query": "q01_kpi_month"},
        {"id": "F4", "metric": "On-time delivery", "value": 41.34, "unit": "%", "period": "2018-01",
         "comparison_value": 42.29, "comparison_period": "2017-12", "delta": -0.95, "delta_unit": "pp",
         "source_query": "q01_kpi_month"},
        {"id": "F5", "metric": "Late orders, First Class", "value": 100.0, "unit": "%", "period": "2018-01",
         "source_query": "q03_delivery_by_mode"},
    ],
}  # fmt: skip

GOOD = (
    "# Review\n\n## Headline\n\nRevenue was $284,672 [F1], down 34.1% [F1]; margin 11.4% [F3].\n\n"
    "## Recommended actions\n\n1. **Logistics lead:** First Class orders are 100.0% late [F5].\n"
)
FABRICATED = "# Review\n\n## Headline\n\nRevenue was $312,000 [F1], down 12% [F1]; margin 14.2% [F3].\n"


class FakeLLM:
    def __init__(self, outputs, name="fake"):
        self.outputs, self.name, self.prompts = list(outputs), name, []

    def generate(self, system, user):
        self.prompts.append(user)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


# ---------------------------------------------------------------- the LLM path


def test_grounded_llm_output_is_accepted_on_the_first_try():
    llm = FakeLLM([GOOD])
    r = review_pack.generate_review(FACTS, [llm])
    assert r.mode == "llm" and r.provider == "fake" and r.text == GOOD
    assert len(r.attempts) == 1 and r.attempts[0]["ok"]


def test_fabricated_numbers_are_rejected_then_retried_with_feedback():
    llm = FakeLLM([FABRICATED, GOOD])
    r = review_pack.generate_review(FACTS, [llm])
    assert r.mode == "llm" and len(r.attempts) == 2
    assert not r.attempts[0]["ok"] and "$312,000" in r.attempts[0]["offending_numbers"]
    retry_prompt = llm.prompts[1]
    assert "rejected by an automatic number checker" in retry_prompt
    assert "$312,000" in retry_prompt and "14.2%" in retry_prompt


def test_two_fabricated_answers_fall_back_to_the_template():
    llm = FakeLLM([FABRICATED, FABRICATED])
    r = review_pack.generate_review(FACTS, [llm])
    assert r.mode == "template" and "failed validation twice" in r.reason
    assert "$312,000" not in r.text and "14.2%" not in r.text
    assert validate(r.text, FACTS["facts"]).ok
    assert [a["provider"] for a in r.attempts] == ["fake", "fake", "template"]


def test_unknown_fact_ids_and_uncited_numbers_are_also_rejected():
    for bad in ("Revenue was $284,672 [F1] and margin 11.4% [F77].", "Revenue was $284,672.\n"):
        r = review_pack.generate_review(FACTS, [FakeLLM([bad, bad])])
        assert r.mode == "template", bad


def test_provider_failure_moves_to_the_next_provider():
    gemini = FakeLLM([RuntimeError("quota exceeded")], name="gemini")
    groq = FakeLLM([GOOD], name="groq")
    r = review_pack.generate_review(FACTS, [gemini, groq])
    assert r.mode == "llm" and r.provider == "groq"
    assert r.attempts[0]["error"].startswith("RuntimeError") and r.attempts[1]["provider"] == "groq"


def test_all_providers_failing_gives_the_template():
    r = review_pack.generate_review(FACTS, [FakeLLM([OSError("down")]), FakeLLM([OSError("down")])])
    assert r.mode == "template" and r.reason == "every provider call failed"


def test_no_llm_mode_never_calls_a_provider():
    llm = FakeLLM([])
    r = review_pack.generate_review(FACTS, [llm], no_llm=True)
    assert r.mode == "template" and llm.prompts == []


def test_no_keys_gives_the_template():
    r = review_pack.generate_review(FACTS, [])
    assert r.mode == "template" and "no LLM API keys" in r.reason


# ---------------------------------------------------------------- providers and config


def test_model_names_come_from_the_environment_not_the_code():
    clients = review_pack.build_clients(
        Env(_env_file=None, gemini_api_key="k1", gemini_model="m1", groq_api_key="k2", groq_model="m2")
    )
    assert [(c.name, c.model) for c in clients] == [("gemini", "m1"), ("groq", "m2")]
    assert review_pack.build_clients(Env(_env_file=None)) == []
    source = (review_pack.__file__ and open(review_pack.__file__, encoding="utf-8").read()).lower()
    assert not re.search(r"gemini-\d|llama-?\d|gpt-\d|mixtral", source), "hard-coded model name"


def test_key_without_model_is_a_configuration_error():
    with pytest.raises(ConfigError, match="GEMINI_MODEL"):
        review_pack.build_clients(Env(_env_file=None, gemini_api_key="k"))
    with pytest.raises(ConfigError, match="GROQ_MODEL"):
        review_pack.build_clients(Env(_env_file=None, groq_api_key="k"))


def test_system_prompt_states_the_grounding_rules():
    p = review_pack.SYSTEM_PROMPT
    assert "ONLY numbers that appear in the facts" in p and "[F3]" in p
    for section in review_pack.SECTIONS:
        assert section in p


# ---------------------------------------------------------------- the deterministic template


def test_template_review_is_grounded_and_has_every_section():
    text = review_pack.template_review(FACTS)
    assert validate(text, FACTS["facts"]).ok
    for heading in ("Headline", "What changed", "Why (drivers)", "Risks", "Recommended actions"):
        assert f"## {heading}" in text
    assert "$284,672" in text and "34.1%" in text


def test_template_survives_missing_fact_groups():
    minimal = {**FACTS, "facts": FACTS["facts"][:1] + FACTS["facts"][2:4]}  # no baseline, no modes, no forecast
    text = review_pack.template_review(minimal)
    assert validate(text, minimal["facts"]).ok


def test_write_pack_records_facts_validation_and_provenance(tmp_path):
    r = review_pack.generate_review(FACTS, [FakeLLM([FABRICATED, GOOD], name="gemini")])
    path = review_pack.write_pack(r, FACTS, tmp_path)
    assert path.name == "review_2018-01.md"
    body = path.read_text(encoding="utf-8")
    assert "drafted by gemini and passed the number check (attempt 2)" in body
    log = json.loads((tmp_path / "review_2018-01.validation.json").read_text())
    assert log["mode"] == "llm" and len(log["attempts"]) == 2 and log["attempts"][0]["ok"] is False
    assert (tmp_path / "review_2018-01.facts.json").exists()


# ---------------------------------------------------------------- facts from SQL


@pytest.fixture
def engine(tables, tmp_path):
    eng = get_engine(Env(_env_file=None, db_backend="sqlite", sqlite_path=str(tmp_path / "k.db")))
    load.load_tables(eng, tables)
    return eng


def test_facts_come_from_the_fixed_queries(engine):
    month = kpis.latest_month(engine)
    doc = kpis.build_facts(engine, month)
    ids = [f["id"] for f in doc["facts"]]
    assert ids == [f"F{i}" for i in range(1, len(ids) + 1)]
    assert doc["period"] == month[:7] and doc["query_checksum"] == kpis.query_checksum()
    assert set(doc["unavailable_queries"]) >= {"q05_forecast_summary", "q07_top_drivers"}  # model tables absent here
    for f in doc["facts"]:
        assert f["source_query"].startswith("q0") and not re.search(r"\d", f["metric"]), f["metric"]
    rev = next(f for f in doc["facts"] if f["metric"] == "Revenue")
    assert rev["unit"] == "USD" and rev["comparison_value"] is not None


def test_revenue_fact_matches_the_sql_view(engine):
    month = kpis.latest_month(engine)
    doc = kpis.build_facts(engine, month)
    rev = next(f for f in doc["facts"] if f["metric"] == "Revenue")
    view = kpis.run_query(engine, "q01_kpi_month", month=month, prev_month="1900-01-01")
    assert rev["value"] == pytest.approx(float(view["revenue"].iloc[0]), abs=0.01)


def test_facts_are_deterministic_and_review_runs_end_to_end(engine, tmp_path):
    month = kpis.latest_month(engine)
    a, b = kpis.build_facts(engine, month), kpis.build_facts(engine, month)
    assert a == b
    result = review_pack.generate_review(a, [], no_llm=True)
    path = review_pack.write_pack(result, a, tmp_path)
    assert path.exists() and validate(result.text, a["facts"]).ok


def test_unknown_month_is_a_clear_error(engine):
    with pytest.raises(ValueError, match="no KPI data"):
        kpis.build_facts(engine, "1999-01-01")


def test_query_checksum_changes_when_a_query_changes(tmp_path, monkeypatch):
    before = kpis.query_checksum()
    fake = tmp_path / "q01.sql"
    fake.write_text("SELECT 1")
    monkeypatch.setattr(kpis, "QUERY_DIR", tmp_path)
    assert kpis.query_checksum() != before


# ---------------------------------------------------------------- CLI


def test_review_pack_cli_runs_without_keys_after_the_pipeline():
    result = runner.invoke(app, ["all", "--sample", "--no-llm"])
    assert result.exit_code == 0, result.output
    assert "review-pack:" in result.output and "template" in result.output
    again = runner.invoke(app, ["review-pack", "--sample", "--no-llm"])
    assert again.exit_code == 0 and "review_" in again.output


def test_cli_reports_a_half_configured_provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_MODEL", "")
    from sca.config import get_env

    get_env.cache_clear()
    try:
        result = runner.invoke(app, ["review-pack", "--sample"])
        assert result.exit_code == 1 and "GEMINI_MODEL" in result.output
    finally:
        get_env.cache_clear()
