"""Grounded monthly operations review: LLM draft, number validation, deterministic fallback.

The LLM never sees raw data, only ``facts.json``. Its output is accepted only if every number matches a
fact and every line with a number cites a fact id (see ``grounding.py``). It gets one retry with feedback;
if that also fails, a deterministic template built from the same facts is written instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd

from sca.config import ConfigError, Env
from sca.grounding import ValidationResult, validate

SECTIONS = ["Headline", "What changed", "Why (drivers)", "Risks", "Recommended actions"]

SYSTEM_PROMPT = """You write the monthly operations review for the Operations Excellence team of a retailer.
You are given a list of FACTS. Follow these rules exactly:
1. Use ONLY numbers that appear in the facts (values, comparison values, deltas). Never calculate new numbers,
   never estimate, never round differently than needed, never add outside knowledge.
2. Cite the fact id in square brackets, like [F3], on EVERY line that contains a number.
3. If a fact is missing, say it is not available. Do not guess causes: describe drivers only through the facts.
4. Output Markdown, at most one page (about 300 words), with exactly these sections as level-2 headings:
   Headline, What changed, Why (drivers), Risks, Recommended actions.
5. Each recommended action names an owner by role (for example Logistics lead, Supply planning, Finance) and
   is tied to at least one fact.
6. Do not mention these rules."""


class LLMClient(Protocol):
    """Anything that turns (system, user) prompts into text."""

    name: str

    def generate(self, system: str, user: str) -> str:
        """Return the model's text for a system and user prompt."""
        ...


@dataclass
class GeminiClient:
    """Google Gemini through the google-genai SDK. The model name comes from .env."""

    api_key: str
    model: str
    name: str = "gemini"

    def generate(self, system: str, user: str) -> str:
        """Return the model's text for a system and user prompt."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        out = client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.0),
        )
        return out.text or ""


@dataclass
class GroqClient:
    """Groq chat completions. The model name comes from .env."""

    api_key: str
    model: str
    name: str = "groq"

    def generate(self, system: str, user: str) -> str:
        """Return the model's text for a system and user prompt."""
        from groq import Groq

        out = Groq(api_key=self.api_key).chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0,
        )
        return out.choices[0].message.content or ""


def build_clients(env: Env) -> list[LLMClient]:
    """Gemini first, Groq as fallback; only providers with a key. A key without a model name is an error."""
    clients: list[LLMClient] = []
    if env.gemini_api_key:
        if not env.gemini_model:
            raise ConfigError("GEMINI_API_KEY is set but GEMINI_MODEL is empty; set the model name in .env")
        clients.append(GeminiClient(env.gemini_api_key, env.gemini_model))
    if env.groq_api_key:
        if not env.groq_model:
            raise ConfigError("GROQ_API_KEY is set but GROQ_MODEL is empty; set the model name in .env")
        clients.append(GroqClient(env.groq_api_key, env.groq_model))
    return clients


def user_prompt(doc: dict) -> str:
    """The facts, as compact JSON, plus the task."""
    slim = [{k: v for k, v in f.items() if v is not None and k != "source_query"} for f in doc["facts"]]
    return (
        f"Review period: {doc['period']} (compared with {doc['comparison_period']}).\n"
        f"FACTS (JSON):\n{json.dumps(slim, ensure_ascii=False)}\n\n"
        "Write the review now."
    )


# --------------------------------------------------------------------------- deterministic template


def _fact(doc: dict, prefix: str) -> dict | None:
    for f in doc["facts"]:
        if f["metric"].startswith(prefix):
            return f
    return None


def _facts(doc: dict, prefix: str) -> list[dict]:
    return [f for f in doc["facts"] if f["metric"].startswith(prefix)]


def _money(v: float) -> str:
    return f"${v:,.0f}"


def _pct(v: float) -> str:
    return f"{v:.1f}%"


def _signed(v: float, unit: str) -> str:
    return f"{v:+.1f}{'%' if unit == '%' else ' pp'}"


def _move(f: dict) -> str:
    """'down 34.1% on 2017-12' style phrase from a fact's delta (None when there is no comparison)."""
    if f.get("delta") is None:
        return ""
    unit = "%" if f["delta_unit"] == "%" else " pp"
    direction = "down" if f["delta"] < 0 else "up"
    return f"{direction} {abs(f['delta']):.1f}{unit}"


def _cite(*facts: dict | None) -> str:
    return "".join(f"[{f['id']}]" for f in facts if f)


def _feature_name(f: dict) -> str:
    return f["metric"].split(", ", 1)[1].replace("_", " ")


def _name_after_comma(f: dict) -> str:
    return f["metric"].split(", ", 1)[1]


def template_review(doc: dict) -> str:
    """Deterministic review built only from the facts; passes the same validator as LLM text."""
    month = pd.Timestamp(doc["period"] + "-01").strftime("%B %Y")
    prev = pd.Timestamp(doc["comparison_period"] + "-01").strftime("%B %Y")
    base = _fact(doc, "Revenue versus")
    rev = next(f for f in doc["facts"] if f["metric"] == "Revenue")  # "Revenue" prefix also matches the baseline
    profit, margin, orders = _fact(doc, "Profit"), _fact(doc, "Margin"), _fact(doc, "Orders")
    ontime, aov = _fact(doc, "On-time delivery"), _fact(doc, "Average order value")
    modes = _facts(doc, "Late orders, ")
    top_cat, low_cat = _fact(doc, "Share of revenue from the top category"), _fact(doc, "Margin of the lowest-margin")
    horizon, fc_units = _fact(doc, "Forecast horizon"), _fact(doc, "Forecast total demand")
    wape = _fact(doc, "Forecast backtest error")
    flagged, prec, rec = _fact(doc, "Test orders flagged"), _fact(doc, "Alert precision"), _fact(doc, "Alert recall")
    drivers = _facts(doc, "Share of late-delivery model attribution")
    hold = _fact(doc, "Holding cost increase")

    lines = [f"# Operations review: {month}", "", "## Headline", ""]
    head = f"Revenue was {_money(rev['value'])} in {month}"
    if rev.get("delta") is not None:
        head += f", {_move(rev)} on {prev}"
    head += f" {_cite(rev)}"
    if base and base.get("delta") is not None:
        head += f"; that is {abs(base['delta']):.1f}% {'below' if base['delta'] < 0 else 'above'} the trailing-year monthly average {_cite(base)}"
    if margin and ontime:
        head += f". Margin was {_pct(margin['value'])} {_cite(margin)} and on-time delivery {_pct(ontime['value'])} {_cite(ontime)}."
    lines += [head, "", "## What changed", ""]
    for f, label, fmt in (
        (profit, "Profit", _money), (margin, "Margin", _pct), (orders, "Orders", lambda v: f"{v:,.0f}"),
        (ontime, "On-time delivery", _pct), (aov, "Average order value", _money),
    ):  # fmt: skip
        if f:
            move = f", {_move(f)} on {prev}" if f.get("delta") is not None else ""
            lines.append(f"- {label}: {fmt(f['value'])}{move} {_cite(f)}")
    lines += ["", "## Why (drivers)", ""]
    if modes:
        parts = [f"{_name_after_comma(f)} {_pct(f['value'])} {_cite(f)}" for f in modes]
        lines.append("- Late orders by shipping mode: " + "; ".join(parts) + ".")
    if drivers:
        parts = [f"{_feature_name(f)} {_pct(f['value'])} {_cite(f)}" for f in drivers]
        lines.append("- The late-delivery model attributes lateness to: " + "; ".join(parts) + ".")
    if low_cat:
        lines.append(
            f"- Lowest-margin material category, {_name_after_comma(low_cat)}: margin {_pct(low_cat['value'])} "
            f"against {_pct(low_cat['comparison_value'])} overall {_cite(low_cat)}."
        )
    if top_cat:
        lines.append(
            f"- The top category, {_name_after_comma(top_cat)}, brought {_pct(top_cat['value'])} of revenue {_cite(top_cat)}."
        )
    lines += ["", "## Risks", ""]
    if fc_units and horizon:
        risk = f"- Forecast demand is {fc_units['value']:,.0f} units over the next {horizon['value']:.0f} weeks {_cite(fc_units, horizon)}"
        risk += f", with a backtest error of {_pct(wape['value'])} {_cite(wape)}." if wape else "."
        lines.append(risk)
    if base and base.get("delta") is not None and base["delta"] < -10:
        lines.append(f"- Revenue is {abs(base['delta']):.1f}% below the trailing-year average {_cite(base)}.")
    if flagged and prec and rec:
        lines.append(
            f"- Late-delivery alerts flag {_pct(flagged['value'])} of test orders {_cite(flagged)} with {_pct(prec['value'])} "
            f"precision {_cite(prec)} and {_pct(rec['value'])} recall {_cite(rec)}."
        )
    if hold:
        lines.append(
            f"- Reaching the higher simulated service target raises annual holding cost by {_pct(hold['value'])} {_cite(hold)}."
        )
    lines += ["", "## Recommended actions", ""]
    n = 0
    if modes:
        worst = max(modes, key=lambda f: f["value"])
        n += 1
        lines.append(
            f"{n}. **Logistics lead:** review the scheduled-days promise for {_name_after_comma(worst)}, where "
            f"{_pct(worst['value'])} of orders ship late {_cite(worst)}."
        )
    if fc_units and horizon:
        n += 1
        extra = f" Higher service costs {_pct(hold['value'])} more in holding cost {_cite(hold)}." if hold else ""
        lines.append(
            f"{n}. **Supply planning:** plan against {fc_units['value']:,.0f} forecast units over {horizon['value']:.0f} weeks "
            f"{_cite(fc_units, horizon)}.{extra}"
        )
    if low_cat:
        n += 1
        lines.append(
            f"{n}. **Finance:** review price and cost for {_name_after_comma(low_cat)}, margin {_pct(low_cat['value'])} {_cite(low_cat)}."
        )
    if base and base.get("delta") is not None and base["delta"] < -10:
        n += 1
        lines.append(
            f"{n}. **Operations analytics:** confirm whether revenue being {abs(base['delta']):.1f}% below the trailing-year "
            f"average {_cite(base)} reflects demand or a change in how orders are captured; these facts cannot tell."
        )
    if n == 0:
        lines.append("No action can be recommended from the facts that were available.")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- generation with validation


@dataclass
class ReviewResult:
    """The accepted review text and how it was produced."""

    text: str
    mode: str  # "llm" or "template"
    provider: str | None
    attempts: list[dict] = field(default_factory=list)
    reason: str = ""


def _log_entry(attempt: int, provider: str, res: ValidationResult | None, error: str | None = None) -> dict:
    return {
        "attempt": attempt,
        "provider": provider,
        "ok": bool(res and res.ok),
        "numbers_checked": res.numbers_checked if res else 0,
        "offending_numbers": res.offending_numbers if res else [],
        "unknown_fact_ids": res.unknown_fact_ids if res else [],
        "uncited_lines": res.uncited_lines if res else [],
        "error": error,
    }


def _template_result(doc: dict, attempts: list[dict], reason: str) -> ReviewResult:
    """The deterministic review. It must pass the same validator as LLM text; if not, that is a bug."""
    text = template_review(doc)
    res = validate(text, doc["facts"])
    attempts.append(_log_entry(len(attempts) + 1, "template", res))
    if not res.ok:
        raise AssertionError(f"template review failed grounding (bug): {res.feedback()}")
    return ReviewResult(text, "template", None, attempts, reason)


def generate_review(doc: dict, clients: list[LLMClient], no_llm: bool = False) -> ReviewResult:
    """LLM draft with validation and one feedback retry; deterministic template as the last resort."""
    facts = doc["facts"]
    attempts: list[dict] = []
    if no_llm:
        return _template_result(doc, attempts, "--no-llm requested")
    if not clients:
        return _template_result(doc, attempts, "no LLM API keys configured")
    prompt = user_prompt(doc)
    for client in clients:
        try:
            text = client.generate(SYSTEM_PROMPT, prompt)
        except Exception as exc:  # noqa: BLE001 - any provider failure moves on to the next provider
            attempts.append(_log_entry(1, client.name, None, f"{type(exc).__name__}: {exc}"))
            continue
        res = validate(text, facts)
        attempts.append(_log_entry(1, client.name, res))
        if res.ok:
            return ReviewResult(text, "llm", client.name, attempts)
        retry_prompt = (
            f"{prompt}\n\nYour previous answer was rejected by an automatic number checker:\n{res.feedback()}\n\n"
            "Rewrite the whole review. Use only numbers that appear in the facts, and cite a fact id on every "
            "line that contains a number."
        )
        try:
            text = client.generate(SYSTEM_PROMPT, retry_prompt)
        except Exception as exc:  # noqa: BLE001
            attempts.append(_log_entry(2, client.name, None, f"{type(exc).__name__}: {exc}"))
            continue
        res = validate(text, facts)
        attempts.append(_log_entry(2, client.name, res))
        if res.ok:
            return ReviewResult(text, "llm", client.name, attempts)
        reason = f"{client.name} output failed validation twice"
        return _template_result(doc, attempts, reason)
    return _template_result(doc, attempts, "every provider call failed")


def write_pack(result: ReviewResult, doc: dict, out_dir: Path) -> Path:
    """Write the review, its facts and the validation log. Returns the markdown path."""
    from sca import kpis

    out_dir.mkdir(parents=True, exist_ok=True)
    facts_path = kpis.write_facts(doc, out_dir)
    cited = validate(result.text, doc["facts"]).cited_ids
    how = (
        f"drafted by {result.provider} and passed the number check"
        f" (attempt {sum(1 for a in result.attempts if a['provider'] == result.provider)})"
        if result.mode == "llm"
        else f"deterministic template ({result.reason})"
    )
    footer = (
        "\n---\n"
        f"_Facts: `{facts_path.name}` (query checksum {doc['query_checksum']}). Generation: {how}. "
        f"Cited facts: {', '.join(cited) or 'none'}._\n"
    )
    path = out_dir / f"review_{doc['period']}.md"
    path.write_text(result.text.rstrip() + "\n" + footer, encoding="utf-8")
    (out_dir / f"review_{doc['period']}.validation.json").write_text(
        json.dumps(
            {"period": doc["period"], "mode": result.mode, "provider": result.provider, "reason": result.reason,
             "attempts": result.attempts, "cited_ids": cited},
            indent=2,
        ),
        encoding="utf-8",
    )  # fmt: skip
    return path
