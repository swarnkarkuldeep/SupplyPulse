import pytest

from sca import grounding as g

FACTS = [
    {"id": "F1", "metric": "Revenue", "value": 284672.01, "unit": "USD", "period": "2018-01",
     "comparison_value": 432004.27, "comparison_period": "2017-12", "delta": -34.1, "delta_unit": "%"},
    {"id": "F2", "metric": "Margin", "value": 11.37, "unit": "%", "period": "2018-01",
     "comparison_value": 15.05, "comparison_period": "2017-12", "delta": -3.68, "delta_unit": "pp"},
    {"id": "F3", "metric": "Orders", "value": 2037.0, "unit": "orders", "period": "2018-01"},
    {"id": "F4", "metric": "Forecast horizon", "value": 12.0, "unit": "weeks", "period": "forecast"},
]  # fmt: skip


def check(text):
    return g.validate(text, FACTS)


# ---------------------------------------------------------------- numbers that must pass


@pytest.mark.parametrize(
    "text",
    [
        "Revenue was $284,672 [F1].",
        "Revenue was $284,672.01 [F1].",
        "Revenue was $285K [F1].",
        "Revenue was $0.3M [F1].",
        "Revenue fell 34.1% [F1] and 34% [F1].",
        "Revenue changed by -34.1% [F1].",
        "Margin was 11.4% [F2], 11% [F2] or 11.37% [F2].",
        "Margin moved -3.7 pp [F2], a fall of 3.7 percentage points [F2].",
        "Last month it was 432,004 [F1] and margin 15.1% [F2].",
        "There were 2,037 orders [F3] over the next 12 weeks [F4].",
    ],
)
def test_grounded_numbers_are_accepted(text):
    res = check(text)
    assert res.ok, res.feedback()
    assert res.numbers_checked >= 1


def test_dates_years_ordinals_and_list_numbering_are_not_data():
    text = (
        "## Headline\n\n"
        "In January 2018 revenue was $284,672 [F1] versus December 2017 [F1] (2018-01 against 2017-12).\n"
        "1. **Finance:** review the 1st category, margin 11.4% [F2].\n"
        "2) Logistics follow up on the 2nd shipping mode, 2,037 orders [F3]."
    )
    res = check(text)
    assert res.ok, res.feedback()


def test_headings_without_numbers_need_no_citation():
    assert check("## Why (drivers)\n\nNo numbers here, only words.").ok


# ---------------------------------------------------------------- fabricated content must fail


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        ("Revenue was $300,000 [F1].", "$300,000"),
        ("Revenue fell 40% [F1].", "40%"),
        ("Margin was 12% [F2].", "12%"),  # rounds to 11, not 12
        ("Margin was 11.9% [F2].", "11.9%"),
        ("There were 3,000 orders [F3].", "3,000"),
        ("Orders rose 5.5% [F3].", "5.5%"),
        ("Revenue was $0.1137M [F1].", "$0.1137M"),
        ("In 2050 there were 2,037 orders [F3].", "2050"),  # a year not named by the facts
        ("Margin was 0.1137 [F2].", "0.1137"),  # fraction instead of percent
    ],
)
def test_fabricated_numbers_are_rejected_and_named(text, bad):
    res = check(text)
    assert not res.ok
    assert any(bad in o or o in bad for o in res.offending_numbers), res.offending_numbers
    assert bad in res.feedback() or any(o in res.feedback() for o in res.offending_numbers)


def test_unknown_fact_ids_are_rejected():
    res = check("Revenue was $284,672 [F1] and orders 2,037 [F99].")
    assert not res.ok and res.unknown_fact_ids == ["F99"]
    assert "F99" in res.feedback()


def test_lines_with_numbers_must_cite_a_fact():
    res = check("Revenue was $284,672 [F1].\nMargin was 11.4% with no citation.")
    assert not res.ok
    assert res.uncited_lines == ["Margin was 11.4% with no citation."]
    assert not res.offending_numbers  # the number is right, only the citation is missing


def test_one_bad_number_among_good_ones_fails_the_whole_text():
    res = check("Revenue $284,672 [F1], margin 11.4% [F2], orders 2,500 [F3].")
    assert not res.ok and res.offending_numbers == ["2,500"]


# ---------------------------------------------------------------- parsing details


def test_extraction_reads_signs_decimals_and_suffixes():
    ms = g.extract_numbers("Down -34.1% and up +3.7 pp, $31.6M, 1,257 orders, $285K")
    by_text = {m.text: m for m in ms}
    assert by_text["-34.1%"].value == -34.1 and by_text["-34.1%"].decimals == 1
    assert by_text["$31.6M"].multiplier == 1e6
    assert by_text["1,257"].value == 1257 and by_text["1,257"].decimals == 0
    assert by_text["$285K"].multiplier == 1e3


def test_citations_are_not_mistaken_for_numbers():
    assert g.extract_numbers("Text [F12] and [F3][F4].") == []


def test_rounding_tolerance_is_half_a_unit_of_the_last_digit():
    cands = [11.37]
    ok = g.Mention("11.4", 11.4, 1, 1.0, 0)
    bad = g.Mention("11.5", 11.5, 1, 1.0, 0)
    assert g.matches(ok, cands) and not g.matches(bad, cands)
    assert g.matches(g.Mention("$285K", 285, 0, 1e3, 0), [284672.01])
    assert not g.matches(g.Mention("$286K", 286, 0, 1e3, 0), [284672.01])


def test_a_number_must_match_a_fact_cited_on_its_own_line():
    # 12 is the value of the horizon fact (F4), but the line cites the margin fact (F2).
    wrong_fact = check("Margin was 12% [F2].")
    assert not wrong_fact.ok and wrong_fact.offending_numbers == ["12%"]
    # Orders (2,037) are a real number but belong to F3, not F1.
    assert check("Orders were 2,037 [F1].").offending_numbers == ["2,037"]
    # Citing the right fact makes the same number acceptable.
    assert check("Horizon is 12 weeks [F4].").ok
    # Several facts on one line may all be quoted.
    assert check("Revenue $284,672 [F1] and orders 2,037 [F3].").ok
