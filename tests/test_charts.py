"""Charts and the price-comparison table on the masked sample."""

from __future__ import annotations

import pandas as pd

from govlens import charts
from govlens import justification as js
from govlens.demo import load_masked_sample
from govlens.engine import analyse, case_items, case_orders

CASES, ORDERS, DETAIL, _ = analyse(*load_masked_sample())


def _case(rule: str) -> pd.Series:
    return CASES[CASES["Rule_ID"] == rule].iloc[0]


def _layer_data(spec: dict) -> list[dict]:
    return [row for ds in spec.get("datasets", {}).values() for row in ds]


def test_g2b_chart_marks_categories_bought_on_both_sides():
    case = CASES[CASES["Case_ID"] == "GL-B86AAAF494B8"].iloc[0]
    spec = charts.g2b_reset_chart(case, case_orders(case, ORDERS), case_items(case, DETAIL)).to_dict()
    rows = [r for r in _layer_data(spec) if "Match" in r]
    both = {r["Category"] for r in rows if r["Match"] == "Category also bought on the other side"}
    assert both == {"Home Appliances"}  # the case's only shared category
    assert "not a breach" in spec["title"]["subtitle"]


def test_g2c_timeline_spans_the_half_year_and_keeps_buyers_anonymous():
    case = _case("G2C")
    spec = charts.g2c_buyer_timeline(case, case_items(case, DETAIL)).to_dict()
    lo, hi = charts._half_year_bounds(case["Period"])
    assert (hi - lo).days in (181, 182, 183)
    rows = _layer_data(spec)
    assert all(r["Buyer"].startswith("Buyer ") for r in rows)
    assert not any("@" in str(v) for r in rows for v in r.values())
    assert sum(r["Orders"] for r in rows) == len(case_orders(case, ORDERS))


def test_half_year_bounds():
    assert charts._half_year_bounds("FY2025-H1") == (pd.Timestamp(2025, 4, 1), pd.Timestamp(2025, 9, 30))
    assert charts._half_year_bounds("FY2025-H2") == (pd.Timestamp(2025, 10, 1), pd.Timestamp(2026, 3, 31))
    assert charts._half_year_bounds("FY2025") is None


def test_dearest_comparisons_are_the_price_band_peers():
    items = js.add_price_bands(js.build_items(ORDERS, DETAIL))
    item = items[items["Price_Escalation"] == 2].iloc[0]
    table = charts.dearest_comparisons(item, items)
    assert len(table) == 5
    assert table["Unit price ($)"].is_monotonic_decreasing
    assert table["Unit price ($)"].iloc[0] == round(item["Peer_Max"], 2)  # top row is the band's maximum
