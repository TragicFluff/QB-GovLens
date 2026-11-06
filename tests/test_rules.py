"""Regression tests for rules, data grain, the knowledge base and retrieval."""

import numpy as np
import pandas as pd
import pytest

from govlens.demo import create_demo, load_masked_sample
from govlens.engine import Settings, analyse, classify_reason, normalize_qb_exports
from govlens.knowledge import (
    KB_DIR, VectorStore, build_retriever, load_knowledge_base, parse_markdown,
)
from govlens.rag import deterministic_explanation, retrieve, validate_citations


def make():
    return create_demo()


# ------------------------------------------------------------------ rules

def test_demo_returns_expected_pattern_severity():
    cases, orders, detail, quality = analyse(*make())
    g2b = cases[cases.Rule_ID.eq("G2B")]
    g2c = cases[cases.Rule_ID.eq("G2C")]
    assert len(g2b) == 2
    assert len(g2c) == 1
    assert g2b[g2b.Subject.str.contains("Ava")].iloc[0].Risk_Tier == "High"
    assert g2b[g2b.Subject.str.contains("Fay")].iloc[0].Risk_Tier == "Low"
    assert g2c.iloc[0].Risk_Tier == "High"
    assert g2c.iloc[0].Total_Amount == 6650
    assert g2c.iloc[0].Distinct_Buyers == 3
    assert quality["cancelled_orders_excluded"] == 1
    assert "CART011" not in "|".join(cases.Evidence_Cart_IDs)
    assert "CART012" not in "|".join(cases.Evidence_Cart_IDs)


def test_event_date_is_order_date():
    _, orders, _, quality = analyse(*make())
    assert (orders["Event_Date"] == orders["Order_Date"]).all()
    assert quality["event_date_basis"].startswith("Order_Date")


def test_only_approved_carts_are_screened():
    inv, carts, items = make()
    carts["Cart_Status"] = "approved"
    carts.loc[carts.Cart_ID.eq("CART001"), "Cart_Status"] = "rejected"
    cases, orders, _, quality = analyse(inv, carts, items)
    assert quality["non_approved_orders_excluded"] == 1
    assert "CART001" not in set(orders.Cart_ID_Effective)
    assert not any((cases.Rule_ID == "G2B") & cases.Subject.str.contains("Ava"))


def test_no_double_count_of_invoice_header_per_item_or_cart():
    inv, carts, items = make()
    extra = items[items.Parent_Invoice_ID.eq("INV001")].copy()
    extra["Amount_After_Discount"] = 50
    items = pd.concat([items, extra], ignore_index=True)
    cases, orders, detail, quality = analyse(inv, carts, items)
    ava = cases[(cases.Rule_ID == "G2B") & cases.Subject.str.contains("Ava")].iloc[0]
    assert ava.Total_Amount == 6700
    assert quality["order_rows_ready"] == 14
    assert orders[orders.Cart_ID_Effective.eq("CART014")].Order_ID.nunique() == 2
    assert orders[orders.Cart_ID_Effective.eq("CART014")].Total_Amt_Payable.sum() == 250


def test_exact_threshold_does_not_flag():
    inv, carts, items = make()
    inv.loc[inv.Invoice_ID.eq("INV002"), "Total_Amt_Payable"] = 2700
    cases, *_ = analyse(inv, carts, items)
    assert not any((cases.Rule_ID == "G2B") & cases.Subject.str.contains("Ava"))


def test_agency_is_always_part_of_g2c_join_key():
    cases, *_ = analyse(*make())
    g2c = cases[cases.Rule_ID.eq("G2C")]
    assert g2c["Agency_Code"].tolist() == ["AG1"]
    assert "kai@example.test" not in g2c.iloc[0]["Evidence_Summary"]


def test_g2b_high_requires_same_pair_category_and_reason():
    inv, carts, items = make()
    buyer = "zed@example.test"
    new = pd.DataFrame([
        ("INV101", "CART101", "2026-03-10", 1750, "Equipment", "lab optics calibration session", "Supplier A"),
        ("INV102", "CART102", "2026-03-11", 1750, "Stationery", "finance induction slide decks", "Supplier B"),
        ("INV103", "CART103", "2026-04-07", 1750, "Equipment", "unrelated motors storage", "Supplier A"),
        ("INV104", "CART104", "2026-04-08", 1750, "Electronics", "finance induction slide decks", "Supplier B"),
    ], columns=["Invoice_ID", "Ref_Cart_ID", "Order_Date", "Total_Amt_Payable",
                "Product_Category", "Reason_For_Purchase", "Seller_Name"])
    inv_new = new[["Invoice_ID", "Ref_Cart_ID", "Order_Date", "Total_Amt_Payable", "Seller_Name"]].copy()
    inv_new["Buyer_Corporate_Email"] = buyer
    inv_new["Buyer_Name"] = "Zed"
    inv_new["Agency_Code"] = "AG1"
    inv_new["Agency_Name"] = "Demo Education Agency"
    inv_new["Cost_Center"] = "CC-ZED"
    inv_new["Cost_Center_Description"] = "Demonstration"
    cart_new = new[["Ref_Cart_ID", "Reason_For_Purchase"]].rename(columns={"Ref_Cart_ID": "Cart_ID"})
    item_new = new[["Invoice_ID", "Product_Category", "Total_Amt_Payable"]].rename(columns={
        "Invoice_ID": "Parent_Invoice_ID", "Total_Amt_Payable": "Amount_After_Discount",
    })
    inv = pd.concat([inv, inv_new], ignore_index=True)
    carts = pd.concat([carts, cart_new], ignore_index=True)
    items = pd.concat([items, item_new], ignore_index=True)
    cases, *_ = analyse(inv, carts, items)
    zed = cases[(cases.Rule_ID == "G2B") & cases.Subject.str.contains("Zed")].iloc[0]
    assert zed.Total_Amount == 7000
    assert zed.Risk_Tier != "High"


def test_missing_cart_not_equivalent_to_blank_purchase_reason():
    inv, carts, items = make()
    carts = carts[~carts.Cart_ID.eq("CART009")].copy()
    cases, _, _, quality = analyse(inv, carts, items)
    assert quality["unmatched_invoice_cart_rows"] == 1
    assert "CART009" not in " | ".join(cases[cases.Rule_ID.eq("REASON")].Evidence_Cart_IDs)


def test_invoices_with_conflicting_duplicate_id_fail_closed():
    inv, carts, items = make()
    duplicate = inv.iloc[[0]].copy()
    duplicate["Total_Amt_Payable"] = 3900
    inv = pd.concat([inv, duplicate], ignore_index=True)
    with pytest.raises(ValueError, match="conflicting duplicate Invoice_ID"):
        analyse(inv, carts, items)


def test_invalid_missing_input_column_is_explicit():
    inv, carts, items = make()
    with pytest.raises(ValueError, match="Buyer_Corporate_Email"):
        normalize_qb_exports(inv.drop(columns="Buyer_Corporate_Email"), carts, items)


@pytest.mark.parametrize("reason, vague, offline", [
    ("QB2025", True, False),
    ("QB buy", True, False),
    ("QB transaction for approval pls", True, True),     # both Governance Guide p.20 examples
    ("Please refer to email from director", False, True),
    ("email subscription for staff newsletters", False, True),  # accepted false alarm
    ("For operations", True, False),
    ("refill for pantry", False, False),
    ("#refillforpantry", False, False),
    ("To replace broken glasses", False, False),
])
def test_reason_rule_follows_guide_keywords(reason, vague, offline):
    got_vague, got_offline, _ = classify_reason(reason)
    assert (got_vague, got_offline) == (vague, offline)


def test_reason_rule_tiers():
    inv, carts, items = make()
    carts.loc[carts.Cart_ID.eq("CART009"), "Reason_For_Purchase"] = "email subscription for staff newsletters"
    cases, *_ = analyse(inv, carts, items)
    reason = cases[cases.Rule_ID.eq("REASON")].set_index("Evidence_Cart_IDs")
    assert reason.loc["CART009", "Risk_Tier"] == "Medium"
    assert "offline approval" in reason.loc["CART009", "Pattern"]
    assert reason.loc["CART010", "Risk_Tier"] == "Medium"   # "approved via email ..."


def test_optional_reason_rule_off():
    cases, *_ = analyse(*make(), settings=Settings(include_reason_check=False))
    assert not cases.Rule_ID.eq("REASON").any()


def test_masked_sample_loads_and_flags_vague_qb2025_reasons():
    cases, orders, detail, quality = analyse(*load_masked_sample())
    assert quality["order_rows_ready"] > 0
    reason = cases[cases.Rule_ID.eq("REASON")]
    assert reason.Evidence_Summary.str.contains("QB2025", case=False).any()


# -------------------------------------------------------- knowledge base

def test_knowledge_base_has_three_sources_and_unique_ids():
    kb = load_knowledge_base()
    docs = {p.doc for p in kb}
    assert docs == {"GG", "DG", "RS"}
    ids = [p.citation for p in kb]
    assert len(ids) == len(set(ids))
    for required in ["GG-CHECK-REASONS", "GG-CHECK-SPLIT", "GG-CHECK-SPEND-PERIOD",
                     "GG-CHECK-TOP-CATEGORY", "DG-ITEM-PRICE-QTY", "RS-G2B", "RS-AI-SCREEN"]:
        assert required in ids
    spend = next(p for p in kb if p.citation == "GG-CHECK-SPEND-PERIOD")
    assert "$6k per officer per 6-month period" in spend.text
    assert spend.location == "p.23"


def test_rule_spec_is_labelled_as_not_policy():
    rs = [p for p in load_knowledge_base() if p.doc == "RS"]
    assert all("not policy" in p.source for p in rs)


def test_parse_markdown_ids_are_stable():
    text = "# T\n\n## [GG-X] Title\npage: 3\n\nBody text.\n"
    one, two = parse_markdown(text), parse_markdown(text)
    assert [p.citation for p in one] == [p.citation for p in two] == ["GG-X"]
    assert one[0].page == "3" and one[0].text == "Body text."


@pytest.mark.parametrize("rule, expected_gg, expected_rs", [
    ("G2B", {"GG-CHECK-SPLIT", "GG-CHECK-SPEND-PERIOD"}, "RS-G2B"),
    ("G2C", {"GG-CHECK-SPLIT"}, "RS-G2C"),
    ("REASON", {"GG-CHECK-REASONS"}, "RS-REASON"),
])
def test_keyword_fallback_retrieves_the_right_guidance(rule, expected_gg, expected_rs):
    retriever = build_retriever(api_key="")
    assert retriever.method == "keyword"
    case = pd.Series({"Rule_ID": rule, "Pattern": "", "Category_Overlap": ""})
    hits = retrieve(retriever, case)
    gg = [h.passage.citation for h in hits if h.passage.doc == "GG"]
    rs = [h.passage.citation for h in hits if h.passage.doc == "RS"]
    assert expected_gg & set(gg[:2])
    assert rs == [expected_rs]
    assert {h.passage.doc for h in hits} == {"GG", "DG", "RS"}


def _fake_embedder(dim: int = 256):
    """Deterministic bag-of-words hashing embedder, standing in for OpenAI in tests."""
    import re
    from hashlib import md5

    calls = {"n": 0}

    def embed(texts):
        calls["n"] += 1
        out = np.zeros((len(texts), dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in re.findall(r"[a-z0-9]+", t.lower()):
                out[i, int(md5(tok.encode()).hexdigest(), 16) % dim] += 1
        return out

    return embed, calls


def test_vector_store_embeds_once_and_reuses_disk_cache(tmp_path):
    embed, calls = _fake_embedder()
    kb = load_knowledge_base(KB_DIR)
    VectorStore.build(kb, embed, "fake-model", tmp_path)
    assert calls["n"] == 1
    assert list(tmp_path.glob("kb_vectors_fake-model_*.npz"))
    VectorStore.build(kb, embed, "fake-model", tmp_path)
    assert calls["n"] == 1  # second build loads from the local vector store


def test_embedding_retriever_returns_scored_hits_per_source(tmp_path):
    embed, _ = _fake_embedder()
    retriever = build_retriever(embed=embed, model="fake-model", cache_dir=tmp_path)
    assert retriever.method == "embedding"
    hits = retriever.search("vague reasons for purchase offline email refer approval", {"GG": 2, "DG": 1, "RS": 1})
    assert [h.passage.doc for h in hits] == ["GG", "GG", "DG", "RS"]
    assert hits[0].passage.citation == "GG-CHECK-REASONS"
    assert all(-1.0 <= h.score <= 1.0 for h in hits)


def test_embedding_failure_degrades_to_keyword(tmp_path):
    def broken(texts):
        raise ConnectionError("offline")
    retriever = build_retriever(embed=broken, model="m", cache_dir=tmp_path)
    assert retriever.method == "keyword"
    assert "failed" in retriever.description


def test_citation_validator():
    kb = load_knowledge_base()
    validate_citations("See [GG-CHECK-SPLIT] and [RS-G2B]. [QB:INV001]", kb)
    with pytest.raises(ValueError, match="verifiable"):
        validate_citations("See [GG-NOT-REAL]", kb)
    with pytest.raises(ValueError, match="verifiable"):
        validate_citations("No citations at all", kb)


def test_deterministic_fallback_makes_no_policy_claim():
    cases, *_ = analyse(*make())
    text = deterministic_explanation(cases[cases.Rule_ID.eq("G2B")].iloc[0])
    assert "not evidence" in text.lower()
    assert "No Governance Guide" in text
