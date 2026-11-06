"""Main page: Governance review with one tab per check (G2B, G2C, Purchase justification).

Loaded by app.py after sign-in. Uses masked/desensitised data only.
"""

from __future__ import annotations

from hashlib import sha256
import io

import pandas as pd
import streamlit as st

from govlens import charts
from govlens import crew
from govlens import justification as js
from govlens import ui
from govlens.demo import load_masked_sample
from govlens.engine import Settings, analyse, case_items, case_orders
from govlens.knowledge import CITATION_RE
from govlens.rag import deterministic_explanation, openai_explanation, retrieve
from govlens.ui_text import DISCLAIMER

SOURCES = ["Masked QB sample (built-in)", "Upload QB CSV exports"]
OFFICER_CAP = 6000.0  # QB's system-enforced spend limit per officer per 6-month period
TIER_ORDER_PJ = {t: i for i, t in enumerate(js.TIER_OPTIONS)}
LEVEL_ORDER = {lvl: -i for i, lvl in enumerate(js.LEVELS)}

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
    CREW_ON = bool(api_key) and crew.available()
    if api_key:
        st.caption(
            f"Models: {ui.CHAT_MODEL} (explanations and AI screen), {ui.EMBEDDING_MODEL} (retrieval). "
            f"Retrieval: {retriever.description}. "
            + ("Case reviews use the CrewAI agent crew." if CREW_ON else "CrewAI is not installed: case reviews use one AI call.")
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

# ------------------------------------------------- purchase justification data
ai_items = js.add_price_bands(js.build_items(orders, item_detail))
ai_eligible = js.eligible_carts(ai_items)
ai_eligible = ai_eligible[ai_eligible["Cart_ID"].isin(agency_orders["Cart_ID_Effective"])]
ai_cache = js.ScreenCache()
ai_results = js.cached_results(ai_items, ai_eligible["Cart_ID"].tolist(), ui.CHAT_MODEL, ai_cache)


def justification_table() -> pd.DataFrame:
    """One row per cart with a single purchase-justification tier and the reasons for it."""
    carts_view = (
        agency_orders.groupby("Cart_ID_Effective", as_index=False)
        .agg(Date=("Event_Date", "min"), Reason_For_Purchase=("Reason_For_Purchase", "first"),
             Cart_Total=("Total_Amt_Payable", "sum"))
        .rename(columns={"Cart_ID_Effective": "Cart_ID"})
    )
    eligible = set(ai_eligible["Cart_ID"])
    rows = [
        js.combined_tier(ai_items, r["Cart_ID"], str(r["Reason_For_Purchase"] or ""),
                         ai_results.get(r["Cart_ID"]), in_scope=r["Cart_ID"] in eligible)
        for _, r in carts_view.iterrows()
    ]
    table = carts_view.merge(pd.DataFrame(rows).drop(columns="Reason_For_Purchase"), on="Cart_ID", how="left")
    table["Date"] = pd.to_datetime(table["Date"]).dt.date
    table["_t"] = table["Tier"].map(TIER_ORDER_PJ)
    table["_l"] = table["Level"].map(LEVEL_ORDER).fillna(1)
    return table.sort_values(["_t", "_l", "Cart_Total"], ascending=[True, True, False]).drop(columns=["_t", "_l"])


justified = justification_table()

k1, k2, k3, k4 = st.columns(4)
k1.metric("G2B cases", f"{(agency_cases['Rule_ID'] == 'G2B').sum():,}")
k2.metric("G2C cases", f"{(agency_cases['Rule_ID'] == 'G2C').sum():,}")
k3.metric("Purchase justification: High", f"{(justified['Tier'] == 'High').sum():,}")
k4.metric("Purchase justification: Medium", f"{(justified['Tier'] == 'Medium').sum():,}")
st.caption(
    "G2B and G2C are rule-based. The purchase-justification tier combines a rule check of the reason "
    "text, an AI assessment of the items and a price comparison; the tab shows why each cart is rated."
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
    linked = case_orders(case, orders)
    linked_items = case_items(case, item_detail)
    if rule_id == "G2B":
        st.altair_chart(charts.g2b_reset_chart(case, linked, linked_items, OFFICER_CAP), use_container_width=True)
    elif rule_id == "G2C":
        st.altair_chart(charts.g2c_buyer_timeline(case, linked_items), use_container_width=True)
    st.markdown("**Orders in this case**")
    linked = linked.assign(Order_Date=linked["Event_Date"].dt.date)
    st.dataframe(
        linked[[
            "Order_Date", "Total_Amt_Payable", "Reason_For_Purchase", "Seller_Name", "Buyer_Corporate_Email",
            "Order_ID", "Cart_ID_Effective",
        ]], hide_index=True, use_container_width=True,
    )
    with st.expander("Items in this case"):
        st.dataframe(
            linked_items[[
                "Order_ID", "Buyer_Corporate_Email", "Cost_Centre_Effective", "Product_Category",
                "Amount_After_Discount", "Item_Desc",
            ]], hide_index=True, use_container_width=True,
        )

    state_key = f"review-{rule_id}"
    report_key = (case_id, raw_fingerprint, kb_fp, settings, bool(api_key), retriever.method)
    if st.button("Review and explain this case", type="primary", key=f"{rule_id}-review"):
        st.session_state[state_key] = run_review(case, case_id, report_key)
    latest = st.session_state.get(state_key)
    if latest and latest["key"] == report_key:
        show_review(case, case_id, latest)


def run_review(case: pd.Series, case_id: str, report_key: tuple) -> dict:
    """Crew first (if available), then a single AI call, then the local explanation."""
    hits = retrieve(retriever, case)
    passages = [h.passage for h in hits]
    result = {"key": report_key, "case_id": case_id, "narrative": deterministic_explanation(case),
              "hits": hits, "engine": "local", "crew": None,
              "note": f"Local explanation (no OpenAI key). Retrieval: {retriever.description}."}
    if not (api_key and passages):
        return result
    crew_problem = ""
    if CREW_ON:
        with st.status("Agent crew: evidence analyst, then guidance researcher, then report writer",
                       expanded=True) as status:
            try:
                run = crew.review_case(case, orders, item_detail, retriever, api_key, ui.CHAT_MODEL,
                                       baseline_hits=hits, progress=ui.status_writer(status))
                status.update(label=f"Crew finished in {run.seconds:.0f}s", state="complete", expanded=False)
                tokens = f", {run.tokens['total_tokens']:,} tokens" if run.tokens.get("total_tokens") else ""
                return {**result, "narrative": run.text, "hits": run.hits, "engine": "crew", "crew": run,
                        "note": (f"Written by a three-agent CrewAI crew ({ui.CHAT_MODEL}) in {run.seconds:.0f}s with "
                                 f"{len(run.tool_calls)} tool calls{tokens}. Every citation was checked against "
                                 f"the passages retrieved in this run. Retrieval: {retriever.description}.")}
            except Exception as exc:
                crew_problem = f"The crew did not return a verified report ({str(exc)[:200]}). "
                status.update(label="Crew did not return a verified report; using a single AI call",
                              state="error", expanded=False)
    try:
        narrative = openai_explanation(case, orders, item_detail, passages, api_key, model=ui.CHAT_MODEL)
        return {**result, "narrative": narrative, "engine": "single",
                "note": (f"{crew_problem}AI-written explanation (one {ui.CHAT_MODEL} call); every citation verified "
                         f"against the retrieved passages. Retrieval: {retriever.description}.")}
    except Exception as exc:
        result["note"] = (f"{crew_problem}AI did not return a verified explanation ({exc}); showing the local "
                          f"explanation. Retrieval: {retriever.description}.")
        return result


def show_review(case: pd.Series, case_id: str, latest: dict) -> None:
    st.divider()
    st.subheader("Review report")
    st.markdown(ui.md(latest["narrative"]))
    st.caption(latest["note"])
    run = latest.get("crew")
    if run is not None:
        with st.expander(f"How the crew worked ({len(run.tool_calls)} tool calls, {run.seconds:.0f}s)"):
            st.markdown("**Tool calls, in order**")
            st.markdown("\n".join(
                f"{i}. `{c['tool']}` " + ", ".join(f"{k} = {v}" for k, v in c["args"].items())
                for i, c in enumerate(run.tool_calls, 1)
            ) or "None")
            for step, title in zip(run.steps, ["Evidence analyst: facts", "Guidance researcher: passages"]):
                st.markdown(f"**{title}**")
                st.markdown(ui.md(step["output"]))
    if latest["hits"]:
        cited = {c for c in CITATION_RE.findall(latest["narrative"])}
        label = ("Knowledge-base passages retrieved in this run (check citations here)"
                 + (f"; {len(cited)} cited" if cited else ""))
        with st.expander(label, expanded=run is None):
            ui.show_hits(sorted(latest["hits"], key=lambda h: h.passage.citation not in cited))
    qa = ask_about_case(case, case_id, latest)
    ui.reviewer_notes(
        case_id,
        {"case": {k: str(v) for k, v in case.items()}, "explanation": latest["narrative"],
         "explanation_engine": latest.get("engine", ""),
         "agent_tool_calls": run.tool_calls if run is not None else [],
         "follow_up_questions": [{"question": q["question"], "answer": q["answer"]} for q in qa],
         "source_passage_ids": [h.passage.citation for h in latest["hits"]],
         "retrieval": retriever.description, "knowledge_base_fingerprint": kb_fp},
        f"govlens_review_{case_id}",
    )


def ask_about_case(case: pd.Series, case_id: str, latest: dict) -> list[dict]:
    """Follow-up questions answered by a tool-using agent; returns this case's Q&A history."""
    history_key = f"qa-{case_id}-{latest['key'][1]}"
    history: list[dict] = st.session_state.setdefault(history_key, [])
    st.markdown("**Ask about this case**")
    if not CREW_ON:
        st.caption("Follow-up questions use the agent crew, which needs an OpenAI key and CrewAI installed.")
        return history
    for item in history:
        st.markdown(ui.md(f"**Q:** {item['question']}"))
        st.markdown(ui.md(item["answer"]))
        st.caption(item["note"])
    with st.form(f"qa-form-{case_id}", clear_on_submit=True):
        question = st.text_input(
            "Question", max_chars=crew.MAX_QUESTION_CHARS, label_visibility="collapsed",
            placeholder="E.g. Did any buyer order from the same seller on the same day?",
        )
        asked = st.form_submit_button("Ask")
    if asked and question.strip():
        with st.status("Case Q&A agent is checking the data and guidance", expanded=True) as status:
            try:
                run = crew.answer_question(
                    question, case, orders, item_detail, retriever, api_key, ui.CHAT_MODEL,
                    baseline_hits=latest["hits"], history=[(h["question"], h["answer"]) for h in history],
                    progress=ui.status_writer(status),
                )
                status.update(label=f"Answered in {run.seconds:.0f}s", state="complete", expanded=False)
                history.append({"question": question, "answer": run.text,
                                "note": f"{len(run.tool_calls)} tool call{'' if len(run.tool_calls) == 1 else 's'}; citations checked."})
                st.rerun()
            except Exception as exc:
                status.update(label="No verified answer", state="error", expanded=True)
                st.warning(f"The agent could not give an answer that passed the citation check ({str(exc)[:200]}). "
                           "Try rephrasing the question.")
    return history


g2b_tab, g2c_tab, pj_tab = st.tabs([
    "G2B: Spend across the 6-month reset", "G2C: Same cost centre and category", "Purchase justification",
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

with pj_tab:
    st.markdown(
        "**What this checks:** whether each cart's reason for purchase justifies what was bought. One tier "
        "per cart, combining three inputs (Governance Guide p.20, p.22 and p.24):  \n"
        "- **Reason check** (Python): flags vague reasons (e.g. 'QB2025') and approval wording such as "
        "offline, email, refer or approval. Approval wording sets a minimum of Medium.  \n"
        "- **AI assessment** (LLM, told about the reason check and given retrieved guidance to cite): whether "
        "each item's core function fits the stated reason. A reason with no stated purpose is a documentation "
        "gap (Medium for everyday items, High for specialised or costly items).  \n"
        "- **Price bands** (Python): items priced between the category's 90th percentile and maximum go up "
        "one tier, above the maximum two tiers.  \n"
        "Tier display: Very High = High; High and Medium = Medium; Low and Very Low = Low. The **Why** column "
        "lists what drove each tier."
    )
    unscreened = [c for c in ai_eligible["Cart_ID"] if c not in ai_results]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Carts", f"{len(justified):,}")
    m2.metric("AI-assessed", f"{len(ai_eligible) - len(unscreened):,} / {len(ai_eligible):,}")
    m3.metric("High", f"{(justified['Tier'] == 'High').sum():,}")
    m4.metric("Medium", f"{(justified['Tier'] == 'Medium').sum():,}")
    if unscreened:
        if api_key:
            st.info(
                f"{len(unscreened)} cart(s) have no AI assessment yet and show a provisional, rule-only tier."
            )
            if st.button(f"Assess {len(unscreened)} cart(s) with {ui.CHAT_MODEL}", type="primary", key="ai-run"):
                bar = st.progress(0.0, text="Retrieving guidance and starting the AI assessment...")
                new, errors = js.screen_carts(
                    ai_items, unscreened, api_key, ui.CHAT_MODEL, ai_cache, retriever=retriever,
                    progress=lambda done, total: bar.progress(done / total, text=f"Assessed {done}/{total} carts"),
                )
                ai_results.update(new)
                if not errors:
                    st.rerun()
                st.warning(f"{len(errors)} cart(s) could not be assessed; they stay provisional and can be retried.")
                with st.expander("Errors"):
                    st.json(errors)
                justified = justification_table()
        else:
            st.warning(
                f"{len(unscreened)} cart(s) have no AI assessment and show a provisional, rule-only tier. "
                "Set OPENAI_API_KEY to assess them."
            )

    tier_filter = st.multiselect("Tier", js.TIER_OPTIONS, default=js.TIER_OPTIONS, key="pj-tier")
    flagged_only = st.checkbox("Only High, Medium and Uncertain", value=True, key="pj-only")
    view = justified[justified["Tier"].isin(tier_filter)]
    if flagged_only:
        view = view[view["Tier"].isin(["High", "Medium", "Uncertain"])]
    st.dataframe(
        view[["Tier", "Why", "Reason_For_Purchase", "Level", "Cart_Total", "Date", "Basis", "Cart_ID"]],
        hide_index=True, use_container_width=True,
    )
    st.download_button(
        "Download this list (CSV)", view.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"qb_govlens_purchase_justification_{selected_agency}_{ui.now_sgt():%Y%m%d_%H%M%S}_SGT.csv",
        mime="text/csv", key="pj-csv",
    )

    if not view.empty:
        labels = {r["Cart_ID"]: f"{r['Tier']} | {r['Reason_For_Purchase']}" for _, r in view.iterrows()}
        cart_id = st.selectbox("Open a cart", list(labels), format_func=labels.get, key="pj-cart")
        row = view[view["Cart_ID"] == cart_id].iloc[0]
        st.markdown(ui.md(
            f"**{row['Tier']}**" + (f" (five-level: {row['Level']})" if row["Level"] else "")
            + f" · {row['Basis']}  \n**Why:** {row['Why']}  \n"
            f"**Reason for purchase:** {row['Reason_For_Purchase'] or '(blank)'}"
        ))
        st.caption(
            "Reason check: " + ("vague reason" if row["Rule_Vague"] else "reason states a purpose")
            + (f"; approval wording found ({row['Approval_Wording']})" if row["Approval_Wording"] else "; no approval wording")
            + "."
        )
        record = ai_results.get(cart_id)
        if record:
            summary, item_rows = js.combine(ai_items, cart_id, record)
            with st.expander("AI assessment and price working", expanded=True):
                st.markdown(ui.md(summary["Assessment"]))
                st.caption(f"Assessed {summary['Assessed_At_SGT']} with {summary['Model']} (prompt {record.get('prompt_version', '')}).")
        else:
            item_rows = ai_items[ai_items["Cart_ID_Effective"] == cart_id]
        item_cols = ["Item_Ref", "Item_Desc", "Product_Category", "Qty_Num", "Unit_Price_After_Discount",
                     "Price_Band", "Peer_Count", "AI_Base_Level", "Escalated_By", "Final_Level",
                     "Core_Function", "AI_Rationale"]
        st.dataframe(item_rows[[c for c in item_cols if c in item_rows.columns]], hide_index=True, use_container_width=True)
        escalated = ai_items[(ai_items["Cart_ID_Effective"] == cart_id) & (ai_items["Price_Escalation"] > 0)]
        if not escalated.empty:
            with st.expander(f"What the price bands compare with ({len(escalated)} item(s) raised on price)", expanded=True):
                st.caption(
                    "Product categories are broad marketplace labels. If the dearest items below are not like the "
                    "item, the price escalation rests on a weak comparison."
                )
                for _, item in escalated.iterrows():
                    st.markdown(ui.md(
                        f"**{item['Item_Ref']} · {item['Product_Category']}:** {str(item['Item_Desc'])[:90]} at "
                        f"${item['Unit_Price_After_Discount']:,.2f} ({item['Price_Band']}; {item['Peer_Count']} "
                        "comparison records). Dearest items it is compared with:"
                    ))
                    st.dataframe(charts.dearest_comparisons(item, ai_items), hide_index=True, use_container_width=True)
        knowledge_by_id = {p.citation: p for p in retriever.passages}
        cited = [knowledge_by_id[c] for c in (record or {}).get("citations", []) if c in knowledge_by_id]
        if cited:
            with st.expander(f"Guidance cited by the AI ({len(cited)} passage(s))"):
                for passage in cited:
                    st.markdown(f"**[{passage.citation}] {passage.title}**  \n*{passage.source}, {passage.location}*")
                    st.markdown(ui.md(passage.text))
        else:
            with st.expander("Related guidance (retrieved from the knowledge base)"):
                query = js.guidance_query(ai_items, cart_id) if cart_id in set(ai_items["Cart_ID_Effective"]) else row["Reason_For_Purchase"]
                ui.show_hits(ui.related_guidance(retriever, f"{kb_fp}|{retriever.method}", query, tuple(js.GUIDANCE_PER_DOC.items())))
        ui.reviewer_notes(
            f"cart-{cart_id}",
            {"cart_id": cart_id, "reason_for_purchase": row["Reason_For_Purchase"], "tier": row["Tier"],
             "level": row["Level"], "why": row["Why"], "basis": row["Basis"],
             "ai_assessment": summary["Assessment"] if record else "",
             "cited_passages": (record or {}).get("citations", [])},
            f"govlens_purchase_justification_{cart_id}",
        )
