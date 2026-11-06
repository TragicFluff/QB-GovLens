"""Tests for the AI justification screen: price bands, escalation, mapping, caching."""

import pandas as pd
import pytest

from govlens import justification as js
from govlens.demo import create_demo, load_masked_sample
from govlens.engine import analyse


def items_frame(rows):
    """rows: (cart, category, unit_price[, qty, welfare])"""
    records = []
    for i, row in enumerate(rows):
        cart, category, price = row[:3]
        qty = row[3] if len(row) > 3 else 1
        welfare = row[4] if len(row) > 4 else False
        records.append({
            "Cart_ID_Effective": cart, "Order_ID": f"O{i}", "Item_Row_Ref": str(i),
            "Product_Category": category, "Amount_After_Discount": price * qty, "Qty": str(qty),
            "Reason_For_Purchase": "pantry refill", "Agency_Code": "AG", "Event_Date": pd.Timestamp("2025-05-01"),
            "Welfare": welfare, "Item_Desc": f"item {i}", "Item_Desc_Details": pd.NA,
        })
    detail = pd.DataFrame(records)
    orders = detail.drop_duplicates("Cart_ID_Effective")[["Cart_ID_Effective"]].copy()
    return js.add_price_bands(js.build_items(orders, detail))


def peers(n, price=10.0):
    return [(f"P{i}", "Snacks", price + i) for i in range(n)]


def test_unit_price_is_after_discount_and_qty():
    it = items_frame([("C1", "Snacks", 4.0, 5)])
    assert it.iloc[0]["Unit_Price_After_Discount"] == 4.0


def test_more_than_max_is_possible_because_own_cart_is_excluded():
    it = items_frame(peers(6) + [("C1", "Snacks", 999.0)])
    row = it[it.Cart_ID_Effective.eq("C1")].iloc[0]
    assert row.Peer_Count == 6
    assert row.Price_Band == "more than maximum"
    assert row.Price_Escalation == 2


def test_five_or_fewer_records_means_no_price_step():
    it = items_frame(peers(5) + [("C1", "Snacks", 999.0)])
    row = it[it.Cart_ID_Effective.eq("C1")].iloc[0]
    assert not row.More_Than_5_Records
    assert row.Price_Escalation == 0


def record(cart, levels):
    return {
        "cart_id": cart, "model": "fake", "assessment": "a", "assessment_summary": "s",
        "items": [{"item_ref": f"I{i + 1}", "core_function": "f", "base_risk_level": lvl, "rationale": "r"}
                  for i, lvl in enumerate(levels)],
    }


@pytest.mark.parametrize("price, base, expected_final, expected_display", [
    (999.0, "Low", "High", "Medium"),            # above max: +2
    (14.9, "Low", "Medium", "Medium"),           # peers 10..15: P90 14.5 < 14.9 <= max: +1
    (14.2, "Low", "Low", "Low"),                 # Q3 13.75 < 14.2 <= P90 14.5: no step
    (10.0, "Low", "Low", "Low"),                 # below Q1: no change
    (999.0, "Very High", "Very High", "High"),   # capped
    (999.0, "High", "Very High", "High"),
    (999.0, "Uncertain", "Uncertain", "Uncertain"),
])
def test_escalation_cap_and_display_mapping(price, base, expected_final, expected_display):
    it = items_frame(peers(6) + [("C1", "Snacks", price)])
    summary, rows = js.combine(it, "C1", record("C1", [base]))
    assert summary["Risk_Level"] == expected_final
    assert summary["Display_Tier"] == expected_display
    assert "Price working (computed by GovLens, not the AI)" in summary["Assessment"]


def test_cart_takes_highest_item_and_names_high_items():
    it = items_frame(peers(6) + [("C1", "Snacks", 10.0), ("C1", "Snacks", 999.0)])
    summary, rows = js.combine(it, "C1", record("C1", ["Low", "Medium"]))
    assert summary["Risk_Level"] == "Very High"
    assert summary["AI_Base_Level"] == "Medium"
    assert summary["Price_Escalated"]
    assert "I2" in summary["Assessment"].split("Items at High or above")[1]


def test_welfare_carts_are_excluded_from_scope():
    it = items_frame([("C1", "Snacks", 5.0, 1, True), ("C2", "Snacks", 5.0)])
    assert js.eligible_carts(it)["Cart_ID"].tolist() == ["C2"]


def test_payload_sends_no_price_band_and_chunks_large_carts():
    it = items_frame([("C1", "Snacks", 1.0 + i) for i in range(30)])
    payloads = js.cart_payloads(it, "C1")
    assert [len(p["items"]) for p in payloads] == [25, 5]
    assert "unit_price_location" not in str(payloads) and "Price_Band" not in str(payloads)


def test_validate_output_rejects_missing_items():
    payload = {"items": [{"item_ref": "I1"}, {"item_ref": "I2"}]}
    with pytest.raises(ValueError, match="item_refs"):
        js.validate_output(payload, record("C1", ["Low"]))


def test_screen_uses_cache_and_isolates_failures(tmp_path):
    it = items_frame([("C1", "Snacks", 1.0), ("C2", "Snacks", 2.0), ("BAD", "Snacks", 3.0)])
    calls = []

    def fake_call(payload, api_key, model):
        calls.append(payload["cart_id"])
        if payload["cart_id"] == "BAD":
            raise RuntimeError("boom")
        return record(payload["cart_id"], ["Low"])

    cache = js.ScreenCache(tmp_path)
    results, errors = js.screen_carts(it, ["C1", "C2", "BAD"], "k", "m", cache, call=fake_call)
    assert set(results) == {"C1", "C2"} and set(errors) == {"BAD"}
    js.screen_carts(it, ["C1", "C2"], "k", "m", cache, call=fake_call)
    assert sorted(calls) == ["BAD", "C1", "C2"]  # cached carts were not re-sent
    assert set(js.cached_results(it, ["C1", "C2", "BAD"], "m", cache)) == {"C1", "C2"}
    table = js.results_table(it, results)
    assert set(table.columns) >= {"Cart_ID", "Display_Tier", "Risk_Level", "Assessment_Summary"}


def test_prompt_keeps_users_framework_and_moves_price_escalation_to_code():
    p = js.SYSTEM_PROMPT
    assert "Father's Day sticker" in p and "public scrutiny test" in p
    assert "do NOT apply any price escalation" in p
    assert "Brand TIER is different from a marketing theme" in p
    assert js.OUTPUT_SCHEMA["properties"]["items"]["items"]["properties"]["base_risk_level"]["enum"][-1] == "Uncertain"


@pytest.mark.parametrize("loader", [create_demo, load_masked_sample])
def test_builds_on_real_and_fictitious_data(loader):
    _, orders, detail, _ = analyse(*loader())
    it = js.add_price_bands(js.build_items(orders, detail))
    assert not it.empty
    assert set(js.eligible_carts(it)["Cart_ID"]) <= set(orders["Cart_ID_Effective"])
