"""Main page: Governance review with one tab per check (G2B, G2C, Reason & justification).

Loaded by app.py after sign-in. Uses masked/desensitised data only.
"""

from __future__ import annotations

from hashlib import sha256
import io

import pandas as pd
import streamlit as st

from govlens import justification as js
from govlens import ui
from govlens.demo import load_masked_sample
from govlens.engine import Settings, analyse, case_items, case_orders
from govlens.rag import deterministic_explanation, openai_explanation, retrieve
from govlens.ui_text import DISCLAIMER

SOURCES = ["Masked QB sample (built-in)", "Upload QB CSV exports"]
OFFICER_CAP = 6000.0  # QB's system-enforced spend limit per officer per 6-month period
REASON_LABELS = {
    "Uninformative purchase reason": "Vague reason",
    "Possible offline approval reference": "Approval keyword",
    "Vague reason and possible offline approval reference": "Vague + approval keyword",
}
RULE_FLAG_OPTIONS = ["Vague + approval keyword", "Approval keyword", "Vague reason", "None"]
AI_TIER_OPTIONS = ["High", "Medium", "Uncertain", "Low", "Not screened", "Out of scope (#welfare)"]
AI_ORDER = {t: i for i, t in enumerate(AI_TIER_OPTIONS)}
RULE_ORDER = {"Medium": 0, "Low": 1, "": 2}

st.title("QB GovLens")
st.caption("Governance review for QuickBuy@SGov agency administrators")
with st.expander("IMPORTANT NOTICE", expanded=True):
    st.markdown(DISCLAIMER)
    st.caption(
        "Masked/desensitised data only. Every output is a review aid, not a finding: a human "
        "administrator decides what it means and what happens next."
    )

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Data source")
    mode = st.radio("Choose data", SOURCES)
    raw_fingerprint = mode
    if mode == SOURCES[1]:
        st.caption("Upload three matching, **desensitised** QB export files.")
        invoice_file = st.file_uploader("QB Invoices file", type="csv", key="inv")
        cart_file = st.file_uploader("QB Carts file", type="csv", key="cart")
        item_file = st.file_uploader("QB InvoiceItems file", type="csv", key="items")
        if not all([invoice_file, cart_file, item_file]):
            st.info("All three files are required. Switch to the masked sample to explore immediately.")
            st.stop()
        invoice_bytes, cart_bytes, item_bytes = invoice_file.getvalue(), cart_file.getvalue(), item_file.getvalue()
        raw_fingerprint = sha256(invoice_bytes + cart_bytes + item_bytes).hexdigest()[:16]
        try:
            invoices = pd.read_csv(io.BytesIO(invoice_bytes), dtype="string")
            carts = pd.read_csv(io.BytesIO(cart_bytes), dtype="string")
            items = pd.read_csv(io.BytesIO(item_bytes), dtype="string")
        except Exception as exc:
            st.error(f"Could not read CSV inputs: {exc}")
            st.stop()
    else:
        try:
            invoices, carts, items = load_masked_sample()
        except FileNotFoundError as exc:
            st.error(str(exc))
            st.stop()
        st.caption(f"{len(invoices):,} invoices, {len(carts):,} carts, {len(items):,} items (masked QB exports).")

    st.divider()
    st.header("Detection settings")
    refresh_days = st.slider("G2B: days each side of the 1 Apr / 1 Oct reset", min_value=7, max_value=60, value=30)
    cc_threshold = st.number_input("G2C: cost-centre screening amount ($)", min_value=100.0, value=6000.0, step=100.0)
    min_reason_tokens = st.slider("G2B/G2C: minimum meaningful words shared between reasons", min_value=1, max_value=5, value=2)
    st.caption("The QB officer spend limit is fixed at $6,000 per 6-month period (system-enforced).")
    settings = Settings(
        officer_cap=OFFICER_CAP, refresh_window_days=refresh_days,
        cost_centre_threshold=cc_threshold, min_reason_shared_tokens=min_reason_tokens,
    )

    st.divider()
    st.header("AI")
    api_key = ui.api_key()
    retriever, kb_fp = ui.retriever(api_key)
    if api_key:
        st.caption(
            f"Models: {ui.CHAT_MODEL} (explanations and AI screen), {ui.EMBEDDING_MODEL} (retrieval). "
            f"Retrieval: {retriever.description}."
        )
    else:
        st.warning("OPENAI_API_KEY not set: keyword retrieval only; AI explanations and the AI screen are off.")

# ---------------------------------------------------------------- analysis
try:
    cases, orders, item_detail, quality = analyse(invoices, carts, items, settings)
except (ValueError, KeyError, TypeError) as exc:
    st.error(f"Data validation failed: {exc}")
    st.stop()

agencies = orders[["Agency_Code", "Agency_Name"]].drop_duplicates().sort_values(["Agency_Name", "Agency_Code"])
if agencies.empty:
    st.warning("No valid approved, non-cancelled QB orders in the supplied dataset.")
    st.stop()
agency_names = dict(zip(agencies["Agency_Code"], agencies["Agency_Name"]))
agency_options = agencies["Agency_Code"].astype(str).tolist()
if len(agency_options) > 1:
    selected_agency = st.selectbox(
        "Agency under review (prototype selector, not access control)", agency_options,
        format_func=lambda code: f"{agency_names.get(code, code)} ({code})",
    )
else:
    selected_agency = agency_options[0]
    st.caption(f"Agency: {agency_names.get(selected_agency, selected_agency)} ({selected_agency})")

agency_orders = orders[orders["Agency_Code"] == selected_agency].copy()
agency_cases = cases[cases["Agency_Code"] == selected_agency].copy()
fy_options = sorted(
    {str(p).split("-", 1)[0] for p in agency_cases["Period"].dropna()} | set(agency_orders["FY"].dropna().astype(str)),
    reverse=True,
)
selected_fys = st.multiselect("Financial year", fy_options, default=fy_options)
agency_cases = agency_cases[
    agency_cases["Period"].astype(str).apply(lambda period: any(period.startswith(fy) for fy in selected_fys))
].copy()
agency_orders = agency_orders[agency_orders["FY"].astype(str).isin(selected_fys)].copy()

# --------------------------------------------- reason & justification data
ai_items = js.add_price_bands(js.build_items(orders, item_detail))
ai_eligible = js.eligible_carts(ai_items)
ai_eligible = ai_eligible[ai_eligible["Cart_ID"].isin(agency_orders["Cart_ID_Effective"])]
ai_cache = js.ScreenCache()
ai_results = js.cached_results(ai_items, ai_eligible["Cart_ID"].tolist(), ui.CHAT_MODEL, ai_cache)


def reason_table() -> pd.DataFrame:
    """One row per cart: deterministic REASON flag and AI-suggested tier, side by side."""
    base = (
        agency_orders.groupby("Cart_ID_Effective", as_index=False)
        .agg(Date=("Event_Date", "min"), Reason_For_Purchase=("Reason_For_Purchase", "first"),
             Cart_Total=("Total_Amt_Payable", "sum"))
        .rename(columns={"Cart_ID_Effective": "Cart_ID"})
    )
    reason_cases = agency_cases[agency_cases["Rule_ID"] == "REASON"].set_index("Evidence_Cart_IDs")
    base["Rule_Flag"] = base["Cart_ID"].map(reason_cases["Pattern"].map(REASON_LABELS)).fillna("None")
    base["Rule_Tier"] = base["Cart_ID"].map(reason_cases["Risk_Tier"]).fillna("")
    base["Rule_Keywords"] = base["Cart_ID"].map(reason_cases["Reason_Overlap"]).fillna("")
    screened = js.results_table(ai_items, {c: ai_results[c] for c in ai_eligible["Cart_ID"] if c in ai_results})
    screened = screened.set_index("Cart_ID") if not screened.empty else pd.DataFrame()
    eligible = set(ai_eligible["Cart_ID"])

    def ai_tier(cart_id: str) -> str:
        if cart_id not in eligible:
            return "Out of scope (#welfare)"
        if not screened.empty and cart_id in screened.index:
            return screened.at[cart_id, "Display_Tier"]
        return "Not screened"

    base["AI_Tier"] = base["Cart_ID"].map(ai_tier)
    for target, source, default in [
        ("AI_Five_Level", "Risk_Level", ""), ("AI_Base_Level", "AI_Base_Level", ""),
        ("AI_Price_Escalated", "Price_Escalated", False), ("AI_Summary", "Assessment_Summary", ""),
    ]:
        base[target] = base["Cart_ID"].map(screened[source]).fillna(default) if not screened.empty else default
    base["Date"] = pd.to_datetime(base["Date"]).dt.date
    base["_ai"] = base["AI_Tier"].map(AI_ORDER)
    base["_rule"] = base["Rule_Tier"].map(RULE_ORDER)
    return base.sort_values(["_ai", "_rule", "Cart_Total"], ascending=[True, True, False]).drop(columns=["_ai", "_rule"])


reasons = reason_table()

k1, k2, k3, k4 = st.columns(4)
k1.metric("G2B cases", f"{(agency_cases['Rule_ID'] == 'G2B').sum():,}")
k2.metric("G2C cases", f"{(agency_cases['Rule_ID'] == 'G2C').sum():,}")
k3.metric("Carts with a reason flag (rule)", f"{(reasons['Rule_Flag'] != 'None').sum():,}")
k4.metric("AI-suggested High (separate)", f"{(reasons['AI_Tier'] == 'High').sum():,}")
st.caption(
    "Rule results (G2B, G2C, reason flags) are computed in Python. AI-suggested tiers come from the "
    "justification screen and never change the rule results."
)


# --------------------------------------------------------- G2B / G2C tabs
CASE_COLUMNS = {
    "G2B": ["Risk_Tier", "Score", "Subject", "Boundary", "Total_Amount", "Excess_Above_Threshold",
            "Category_Overlap", "Reason_Overlap", "Case_ID"],
    "G2C": ["Risk_Tier", "Score", "Subject", "Period", "Distinct_Buyers", "Total_Amount",
            "Excess_Above_Threshold", "Reason_Overlap", "Seller_Overlap", "Case_ID"],
}
TIER_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def case_tab(rule_id: str, intro: str) -> None:
    st.markdown(ui.md(intro))
    rule_cases = agency_cases[agency_cases["Rule_ID"] == rule_id].copy()
    if rule_cases.empty:
        st.info("No cases for this check in the selected financial years.")
        return
    tiers = st.multiselect("Review priority", ["High", "Medium", "Low"], default=["High", "Medium", "Low"], key=f"{rule_id}-tiers")
    shown = rule_cases[rule_cases["Risk_Tier"].isin(tiers)].copy()
    shown["_t"] = shown["Risk_Tier"].map(TIER_ORDER)
    shown = shown.sort_values(["_t", "Score", "Total_Amount"], ascending=[True, False, False]).drop(columns="_t")
    st.dataframe(shown[CASE_COLUMNS[rule_id]], hide_index=True, use_container_width=True)
    st.download_button(
        f"Download {rule_id} cases (CSV)", shown.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"qb_govlens_{rule_id}_{selected_agency}_{ui.now_sgt():%Y%m%d_%H%M%S}_SGT.csv",
        mime="text/csv", key=f"{rule_id}-csv",
    )
    if shown.empty:
        return
    labels = {
        r["Case_ID"]: f"{r['Risk_Tier']} | {r['Subject']} | ${float(r['Total_Amount']):,.2f}"
        for _, r in shown.iterrows()
    }
    case_id = st.selectbox("Open a case", list(labels), format_func=labels.get, key=f"{rule_id}-case")
    case = shown[shown["Case_ID"] == case_id].iloc[0]
    st.caption(
        f"Case {case_id} | Priority: {case['Risk_Tier']} | Score: {case['Score']} "
        f"({case['Score_Breakdown']}) | Rule version: {case['Rule_Version']}"
    )
    st.markdown(ui.md(f"**Evidence:** {case['Evidence_Summary']}"))
    st.markdown("**Orders in this case**")
    linked = case_orders(case, orders)
    linked = linked.assign(Order_Date=linked["Event_Date"].dt.date)
    st.dataframe(
        linked[[
            "Order_Date", "Total_Amt_Payable", "Reason_For_Purchase", "Seller_Name", "Buyer_Corporate_Email",
            "Order_ID", "Cart_ID_Effective",
        ]], hide_index=True, use_container_width=True,
    )
    with st.expander("Items in this case"):
        st.dataframe(
            case_items(case, item_detail)[[
                "Order_ID", "Buyer_Corporate_Email", "Cost_Centre_Effective", "Product_Category",
                "Amount_After_Discount", "Item_Desc",
            ]], hide_index=True, use_container_width=True,
        )

    state_key = f"review-{rule_id}"
    report_key = (case_id, raw_fingerprint, kb_fp, settings, bool(api_key), retriever.method)
    if st.button("Review and explain this case", type="primary", key=f"{rule_id}-review"):
        hits = retrieve(retriever, case)
        passages = [h.passage for h in hits]
        narrative = deterministic_explanation(case)
        note = f"Local explanation (no OpenAI key). Retrieval: {retriever.description}."
        if api_key and passages:
            try:
                narrative = openai_explanation(case, orders, item_detail, passages, api_key, model=ui.CHAT_MODEL)
                note = (f"AI-written explanation ({ui.CHAT_MODEL}); every citation verified against the "
                        f"retrieved passages. Retrieval: {retriever.description}.")
            except Exception as exc:
                note = f"AI did not return a verified explanation ({exc}); showing the local explanation. Retrieval: {retriever.description}."
        st.session_state[state_key] = {"key": report_key, "case_id": case_id, "narrative": narrative,
                                       "hits": hits, "note": note}
    latest = st.session_state.get(state_key)
    if latest and latest["key"] == report_key:
        st.divider()
        st.subheader("Review report")
        st.markdown(ui.md(latest["narrative"]))
        st.caption(latest["note"])
        if latest["hits"]:
            with st.expander("Retrieved knowledge-base passages (check citations here)", expanded=True):
                ui.show_hits(latest["hits"])
        ui.reviewer_notes(
            case_id,
            {"case": {k: str(v) for k, v in case.items()}, "explanation": latest["narrative"],
             "source_passage_ids": [h.passage.citation for h in latest["hits"]],
             "retrieval": retriever.description, "knowledge_base_fingerprint": kb_fp},
            f"govlens_review_{case_id}",
        )


g2b_tab, g2c_tab, reason_tab = st.tabs([
    "G2B: Spend across the 6-month reset", "G2C: Same cost centre and category", "Reason & justification",
])

with g2b_tab:
    case_tab("G2B", (
        f"**What this checks:** one officer's spend in the {refresh_days} days before and after each "
        "1 April / 1 October reset of the $6,000 per-officer limit, where the combined amount exceeds "
        "$6,000. A shared product category and shared reason words across the reset raise the priority. "
        "Governance Guide: *Split purchases* (p.21) and the spend limit (p.23)."
    ))

with g2c_tab:
    case_tab("G2C", (
        "**What this checks:** two or more buyers in the same cost centre buying the same product "
        f"category in a half financial year, together above ${cc_threshold:,.0f}. Close timing, shared "
        "reasons, more buyers and recurrence raise the priority. Governance Guide: *Split purchases*, "
        "buyers in the same department (p.21)."
    ))

with reason_tab:
    st.markdown(
        "**What this checks:** each cart's reason for purchase, two ways, shown side by side.  \n"
        "- **Rule flag** (Python, Governance Guide p.20): the reason text alone is vague (e.g. 'QB2025'), "
        "or contains offline, email, refer or approval wording.  \n"
        "- **AI-suggested tier** (LLM plus price bands, Guide p.22 and p.24): whether each item's core "
        "function fits the stated reason; items priced between the category's 90th percentile and maximum "
        "go up one tier, above the maximum two tiers. Display: Very High = High; High and Medium = Medium; "
        "Low and Very Low = Low. The AI result never changes the rule flag."
    )
    unscreened = [c for c in ai_eligible["Cart_ID"] if c not in ai_results]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Carts", f"{len(reasons):,}")
    m2.metric("Rule-flagged", f"{(reasons['Rule_Flag'] != 'None').sum():,}")
    m3.metric("AI-screened", f"{len(ai_eligible) - len(unscreened):,} / {len(ai_eligible):,}")
    m4.metric("AI-suggested High / Medium", f"{(reasons['AI_Tier'] == 'High').sum():,} / {(reasons['AI_Tier'] == 'Medium').sum():,}")
    if api_key and unscreened:
        if st.button(f"Screen {len(unscreened)} unscreened cart(s) with {ui.CHAT_MODEL}", type="primary", key="ai-run"):
            bar = st.progress(0.0, text="Starting AI screen...")
            new, errors = js.screen_carts(
                ai_items, unscreened, api_key, ui.CHAT_MODEL, ai_cache,
                progress=lambda done, total: bar.progress(done / total, text=f"Screened {done}/{total} carts"),
            )
            ai_results.update(new)
            if not errors:
                st.rerun()
            st.warning(f"{len(errors)} cart(s) could not be screened; they stay unscreened and can be retried.")
            with st.expander("Errors"):
                st.json(errors)
            reasons = reason_table()
    elif not api_key:
        st.warning("Set OPENAI_API_KEY to run the AI screen. Rule flags and price bands work without it.")

    f1, f2 = st.columns(2)
    rule_filter = f1.multiselect("Rule flag", RULE_FLAG_OPTIONS, default=RULE_FLAG_OPTIONS, key="reason-rule")
    ai_filter = f2.multiselect("AI-suggested tier", AI_TIER_OPTIONS, default=AI_TIER_OPTIONS, key="reason-ai")
    flagged_only = st.checkbox(
        "Only carts with a rule flag or an AI-suggested High, Medium or Uncertain tier", value=True, key="reason-only",
    )
    view = reasons[reasons["Rule_Flag"].isin(rule_filter) & reasons["AI_Tier"].isin(ai_filter)]
    if flagged_only:
        view = view[(view["Rule_Flag"] != "None") | view["AI_Tier"].isin(["High", "Medium", "Uncertain"])]
    st.dataframe(
        view[["Rule_Flag", "AI_Tier", "Reason_For_Purchase", "AI_Summary", "Rule_Tier", "AI_Five_Level",
              "AI_Price_Escalated", "Cart_Total", "Date", "Cart_ID"]],
        hide_index=True, use_container_width=True,
    )
    st.download_button(
        "Download this list (CSV)", view.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"qb_govlens_reason_justification_{selected_agency}_{ui.now_sgt():%Y%m%d_%H%M%S}_SGT.csv",
        mime="text/csv", key="reason-csv",
    )

    if not view.empty:
        labels = {
            r["Cart_ID"]: f"{r['AI_Tier']} (AI) | {r['Rule_Flag']} (rule) | {r['Reason_For_Purchase']}"
            for _, r in view.iterrows()
        }
        cart_id = st.selectbox("Open a cart", list(labels), format_func=labels.get, key="reason-cart")
        row = view[view["Cart_ID"] == cart_id].iloc[0]
        st.markdown(ui.md(f"**Reason for purchase:** {row['Reason_For_Purchase'] or '(blank)'}"))
        left, right = st.columns(2)
        with left:
            st.markdown("**Rule flag (Python)**")
            if row["Rule_Flag"] == "None":
                st.write("No vague wording or approval keywords found.")
            else:
                st.markdown(ui.md(
                    f"{row['Rule_Flag']} · {row['Rule_Tier']}"
                    + (f"  \nKeywords: {row['Rule_Keywords']}" if row["Rule_Keywords"] else "")
                ))
        with right:
            st.markdown("**AI-suggested tier**")
            if cart_id in ai_results:
                summary, item_rows = js.combine(ai_items, cart_id, ai_results[cart_id])
                st.markdown(ui.md(
                    f"{summary['Display_Tier']} (five-level: {summary['Risk_Level']}; AI base: "
                    f"{summary['AI_Base_Level']})  \n{summary['Assessment_Summary']}"
                ))
            else:
                summary = None
                item_rows = ai_items[ai_items["Cart_ID_Effective"] == cart_id]
                st.write(row["AI_Tier"] + ".")
        if summary:
            with st.expander("AI and price working", expanded=True):
                st.markdown(ui.md(summary["Assessment"]))
        item_cols = ["Item_Ref", "Item_Desc", "Product_Category", "Qty_Num", "Unit_Price_After_Discount",
                     "Price_Band", "Peer_Count"]
        if summary:
            item_cols += ["AI_Base_Level", "Escalated_By", "Final_Level", "Core_Function", "AI_Rationale"]
        st.dataframe(item_rows[[c for c in item_cols if c in item_rows.columns]], hide_index=True, use_container_width=True)
        categories = ", ".join(sorted(set(item_rows["Product_Category"]))) if not item_rows.empty else ""
        query = (
            f"Reason for purchase: {row['Reason_For_Purchase']}. Product categories: {categories}. "
            "Vague reasons or offline approval keywords; whether there was a requirement for purchase; "
            "price reasonableness within product categories."
        )
        with st.expander("Related guidance (retrieved from the knowledge base)"):
            ui.show_hits(ui.related_guidance(retriever, f"{kb_fp}|{retriever.method}", query, (("GG", 2), ("RS", 1))))
        ui.reviewer_notes(
            f"cart-{cart_id}",
            {"cart_id": cart_id, "reason_for_purchase": row["Reason_For_Purchase"],
             "rule_flag": row["Rule_Flag"], "rule_tier": row["Rule_Tier"], "ai_tier": row["AI_Tier"],
             "ai_assessment": summary["Assessment"] if summary else ""},
            f"govlens_reason_{cart_id}",
        )
