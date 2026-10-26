"""Grounding validator: every number in a generated review must come from the facts, and cite them.

Rules
-----
1. Every number in the text must match a fact cited on the same line (its value, comparison value, delta or
   absolute delta) within rounding: a number written with ``d`` decimals matches when it is within half a unit
   of its last written digit. ``K``, ``M`` and ``B`` suffixes are understood (``$285K`` matches 284,672).
2. Numbers that are not data are allowed: the years that appear in the facts' periods, ISO dates, ordinals
   (1st, 2nd), list numbering at the start of a line, and the fact ids themselves.
3. Every fact id cited (``[F3]``) must exist.
4. Every line that contains a data number must cite at least one fact id.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CITATION = re.compile(r"\[F(\d+)\]")
ISO_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")
YEAR_IN_PERIOD = re.compile(r"\b(?:19|20)\d{2}\b")
ORDINAL = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.IGNORECASE)
LIST_PREFIX = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?\d+[.)][ \t]+", re.MULTILINE)
HEADING = re.compile(r"^\s*#+\s")
NUMBER = re.compile(
    r"(?P<sign>[+\-−])?\s?(?P<cur>\$)?(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
    r"(?P<suffix>\s?(?:[KkMmBb]|bn)\b)?(?P<unit>\s?(?:%|pp\b|percentage points?))?",
)
SUFFIX_MULT = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9}


@dataclass
class Mention:
    """A number found in the text."""

    text: str
    value: float
    decimals: int
    multiplier: float
    line: int


@dataclass
class ValidationResult:
    """Outcome of validating one generated text."""

    ok: bool
    offending_numbers: list[str] = field(default_factory=list)
    unknown_fact_ids: list[str] = field(default_factory=list)
    uncited_lines: list[str] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    numbers_checked: int = 0

    def feedback(self) -> str:
        """Plain-language list of problems, sent back to the model on the retry."""
        parts = []
        if self.offending_numbers:
            parts.append(
                "These numbers are not in the facts (or do not match any fact value): "
                + ", ".join(self.offending_numbers)
            )
        if self.unknown_fact_ids:
            parts.append("These fact ids do not exist: " + ", ".join(self.unknown_fact_ids))
        if self.uncited_lines:
            parts.append("These lines contain numbers but cite no fact id like [F3]: " + " | ".join(self.uncited_lines))
        return "\n".join(parts)


def _mask(text: str, years: frozenset[str] = frozenset()) -> str:
    """Blank out text that looks numeric but is not data (ids, dates, allowed years, ordinals, list numbers)."""
    for pattern in (CITATION, ISO_DATE, ORDINAL, LIST_PREFIX):
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    if years:
        alt = "|".join(sorted(years))
        text = re.sub(rf"(?<![\d.,$])(?:{alt})(?![\d%]|\.\d|,\d)", lambda m: " " * len(m.group(0)), text)
    return text


def extract_numbers(text: str, years: frozenset[str] = frozenset()) -> list[Mention]:
    """Find every data number in ``text`` (after masking ids, dates, allowed years, ordinals, list numbering)."""
    out: list[Mention] = []
    for i, line in enumerate(_mask(text, years).splitlines()):
        for m in NUMBER.finditer(line):
            frac = m.group("frac") or ""
            raw = m.group("int").replace(",", "") + frac
            suffix = (m.group("suffix") or "").strip().lower()
            sign = -1.0 if m.group("sign") in ("-", "−") else 1.0
            out.append(
                Mention(m.group(0).strip(), sign * float(raw), max(len(frac) - 1, 0), SUFFIX_MULT.get(suffix, 1.0), i)
            )
    return out


def candidate_values(facts: list[dict]) -> list[float]:
    """Every value a fact lets the text quote: value, comparison, delta and their absolute values."""
    vals: list[float] = []
    for f in facts:
        for key in ("value", "comparison_value", "delta"):
            v = f.get(key)
            if v is not None:
                vals += [float(v), abs(float(v))]
    return vals


def matches(mention: Mention, candidates: list[float]) -> bool:
    """True when the written number could be a rounding of some candidate."""
    written = mention.value * mention.multiplier
    # Half a unit of the last written digit, in the same scale, plus a hair for float noise.
    tol = 0.5 * 10 ** (-mention.decimals) * mention.multiplier * (1 + 1e-9) + 1e-9
    for c in candidates:
        if abs(written - c) <= tol or abs(abs(written) - abs(c)) <= tol:
            return True
    return False


def allowed_years(facts: list[dict]) -> frozenset[str]:
    """Years named by the facts' period labels (for example 2018 from "2018-01")."""
    found: set[str] = set()
    for f in facts:
        for key in ("period", "comparison_period"):
            found.update(YEAR_IN_PERIOD.findall(str(f.get(key) or "")))
    return frozenset(found)


def validate(text: str, facts: list[dict]) -> ValidationResult:
    """Check ``text`` against ``facts`` (the list in facts.json)."""
    ids = {f["id"] for f in facts}
    cited = [f"F{n}" for n in CITATION.findall(text)]
    unknown = sorted({c for c in cited if c not in ids})
    by_id = {f["id"]: f for f in facts}
    everything = candidate_values(facts)
    mentions = extract_numbers(text, allowed_years(facts))
    lines = text.splitlines()
    offending = []
    for m in mentions:
        line = lines[m.line] if m.line < len(lines) else ""
        cited_here = [by_id[f"F{n}"] for n in CITATION.findall(line) if f"F{n}" in by_id]
        # A number must come from a fact cited on its own line; with no citation there is nothing to
        # check it against here (the line is reported as uncited), so fall back to any fact.
        pool = candidate_values(cited_here) if cited_here else everything
        if not matches(m, pool):
            offending.append(m.text)
    uncited = []
    for line_no in sorted({m.line for m in mentions}):
        line = lines[line_no] if line_no < len(lines) else ""
        if not HEADING.match(line) and not CITATION.search(line):
            uncited.append(line.strip()[:80])
    return ValidationResult(
        ok=not (offending or unknown or uncited),
        offending_numbers=offending,
        unknown_fact_ids=unknown,
        uncited_lines=uncited,
        cited_ids=sorted(set(cited), key=lambda x: int(x[1:])),
        numbers_checked=len(mentions),
    )
