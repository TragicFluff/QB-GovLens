"""Methodology page: data flows, implementation, rules, data health, knowledge base, one flowchart per use case."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from govlens import justification as js
from govlens import ui
from govlens.demo import load_masked_sample
from govlens.engine import Settings, analyse
from govlens.flowcharts import FLOW_OVERVIEW, FLOW_UC1, FLOW_UC2
from govlens.knowledge import load_knowledge_base
from govlens.rag import PER_DOC, RULE_QUERIES, SYSTEM_INSTRUCTIONS


@st.cache_data(show_spinner=False)
def _sample_quality() -> dict:
    try:
        return analyse(*load_masked_sample(), Settings())[3]
    except FileNotFoundError:
        return {}


st.title("Methodology")
st.markdown(
    "QB GovLens combines **deterministic rules** (which decide what is flagged), **retrieval-augmented "
    "generation** over official QB guidance (which explains a flag, with verified citations), and an "
    "**LLM judgement step** whose output is post-processed by deterministic price logic and shown beside, "
    "never merged into, the rule result. Colour key in every flowchart: blue = Python, purple = LLM or "
    "embeddings, yellow = administrator action, green = output."
)

st.header("1. Overall data flow")
st.graphviz_chart(FLOW_OVERVIEW, use_container_width=True)
st.markdown(
    "**Purchase data.** Three masked QB Admin Portal exports are loaded: Carts (reason for purchase, "
    "status, welfare flag, cost centre), Invoices (one row per seller order: buyer, seller, Order_Date, "
    "Total_Amt_Payable) and InvoiceItems (item description, product category, quantity, amounts). "
    "Invoices join to carts on `Ref_Cart_ID = Cart_ID` and items to invoices on "
    "`Parent_Invoice_ID = Invoice_ID`. Following the Governance Guide, only **approved, non-cancelled** "
    "carts are screened; `Order_Date` is the event date for every time-window rule; welfare purchases "
    "(`#welfare`) are excluded from G2B, G2C and the AI screen. Invoice totals are counted once per "
    "invoice and item amounts are kept at item grain, so a cart with several sellers or items is never "
    "double-counted.\n\n"
    "**Knowledge base.** The official Governance Guide was curated into one passage per suggested "
    "check or data topic (page numbers kept); the Data Glossary is converted by script, keeping the "
    "official field descriptions verbatim; a GovLens rule specification documents this tool's own "
    "rules and is labelled as *not policy*. Each `## [ID]` section is one passage with a stable "
    f"citation ID. Passages are embedded once with `{ui.EMBEDDING_MODEL}` and stored in a local "
    "NumPy vector store that is rebuilt only when the documents or the embedding model change."
)

st.header("2. Use case 1: split-purchase review with a cited explanation (G2B and G2C tabs)")
st.graphviz_chart(FLOW_UC1, use_container_width=True)
st.markdown(
    "**Detection (Python).** Both rules run over all purchases when the data loads; each has its own tab "
    "listing the flagged cases by priority.\n"
    "- **G2B** (Guide: *Split purchases* p.21; spend limit of \\$6k per officer per 6-month period, p.23): "
    "an officer's spend in the days either side of 1 April / 1 October (30 by default) that together "
    "exceeds the \\$6,000 limit; a shared product category and shared reason words raise the priority.\n"
    "- **G2C** (Guide: buyers in the same department buying the same category, p.21): two or more "
    "material buyers in one cost centre and product category within a half financial year, together "
    "above the screening amount (\\$6,000 by default); timing, shared reasons, buyer count and recurrence "
    "raise the priority.\n\n"
    "**Retrieval.** When the administrator clicks *Review and explain this case*, a natural-language "
    "query is built from the rule's definition, the case pattern and any shared categories. The query is "
    "embedded and compared with every passage by cosine similarity; the top "
    f"{PER_DOC['GG']} Governance Guide, {PER_DOC['DG']} Data Glossary and {PER_DOC['RS']} rule-spec "
    "passages are kept, so each explanation draws on policy, terminology and the rule's own logic. "
    "Without an API key, a keyword retriever is used and the sidebar says so.\n\n"
    "**Generation and validation.** The case, its linked order and item rows, and the retrieved "
    "passages are sent to the chat model with instructions to explain (never to re-score or accuse), "
    "to cite each guidance claim with a passage ID and each transaction with its order ID, and to say "
    "*'Not established by the supplied references'* when the passages do not support a claim. "
    "GovLens then checks every cited ID against the retrieved set; if any citation is unknown or "
    "missing, the AI text is discarded and a local evidence-only narrative is shown instead. The "
    "retrieved passages are always displayed under the report so the reviewer can verify them."
)
with st.expander("System instructions used for the explanation"):
    st.code(SYSTEM_INSTRUCTIONS, language="text")

st.header("3. Use case 2: reason & justification (one tab)")
st.graphviz_chart(FLOW_UC2, use_container_width=True)
st.markdown(
    "Each cart gets two independent results, shown side by side and never merged.\n\n"
    "**Rule flag (Python; Guide p.20, anomalies in reasons for purchase).** The REASON rule reads only "
    "the reason text. Vague reasons (e.g. 'QB2025', 'QB buy', fewer than two meaningful words without a "
    "purpose hashtag) are Low; offline, email, refer or approval wording, which can suggest approval "
    "sought outside QB, is Medium. The rule is deliberately broad.\n\n"
    "**AI-suggested tier (LLM plus Python; Guide p.22 requirement for purchase, p.24 price "
    "reasonableness).** Each cart in scope is sent to the chat model as JSON: the reason for purchase and "
    "each item's category, description, quantity and prices. The prompt asks the model to identify each "
    "item's core function (ignoring marketing themes but not luxury brand tier), judge whether that "
    "function can serve the stated purpose, and assign a base level from Very Low to Very High, or "
    "Uncertain. The response must match a strict JSON schema; GovLens rejects it unless every item is "
    "returned with an allowed level. Carts with more than 25 items are sent in parts.\n\n"
    "**Price escalation (Python).** Unit price after discount (`Amount_After_Discount / Qty`) is "
    "compared with items from *other* carts in the same `Product_Category` across all agencies. With "
    "more than 5 comparison records, an item between the 90th percentile and the maximum is escalated "
    "by one tier and an item above the maximum by two tiers, capped at Very High. Price never lowers "
    "a level and Uncertain items are not escalated. Price bands are deliberately **not** sent to the "
    "model, so the arithmetic is transparent and testable.\n\n"
    "**Why both.** The two overlap only where a vague reason leaves the items unexplained. The rule "
    "alone catches approval wording, which the AI prompt does not look for; the AI alone catches a "
    "specific reason that does not fit the items bought."
)
st.dataframe(
    pd.DataFrame({
        "Five-level AI result": ["Very High", "High", "Medium", "Low", "Very Low", "Uncertain"],
        "Display tier": [js.DISPLAY_TIER[k] for k in ["Very High", "High", "Medium", "Low", "Very Low", "Uncertain"]],
    }),
    hide_index=True,
)
with st.expander("Justification prompt used for the AI screen"):
    st.code(js.SYSTEM_PROMPT, language="text")
with st.expander("Required JSON output schema"):
    st.json(js.OUTPUT_SCHEMA)

st.header("4. Data health, knowledge base and retrieval check")
quality = _sample_quality()
if quality:
    labels = {
        "invoice_rows_loaded": "Invoice rows loaded", "cart_rows_loaded": "Cart rows loaded",
        "item_rows_loaded": "Item rows loaded", "unmatched_invoice_cart_rows": "Invoices with no matching cart",
        "cancelled_orders_excluded": "Orders excluded: cancelled carts",
        "non_approved_orders_excluded": "Orders excluded: carts not approved",
        "invalid_or_nonpositive_items_excluded": "Items excluded: zero or invalid amount",
        "items_without_invoice_excluded": "Items excluded: no matching invoice",
        "orders_without_item_rows": "Orders with no item rows", "missing_item_cost_centres": "Items with no cost centre",
        "order_rows_ready": "Orders screened", "item_rows_ready": "Items screened",
        "event_date_basis": "Event date used",
    }
    st.markdown("**Masked sample: data coverage**")
    st.dataframe(
        pd.DataFrame([{"Check": labels.get(k, k), "Value": str(v)} for k, v in quality.items()]),
        hide_index=True, use_container_width=True,
    )
knowledge = load_knowledge_base()
st.markdown("**Knowledge-base passages**")
st.dataframe(
    pd.DataFrame([
        {"Citation": p.citation, "Source": p.source, "Location": p.location, "Title": p.title} for p in knowledge
    ]),
    hide_index=True, use_container_width=True,
)
retriever, kb_fp = ui.retriever(ui.api_key())
st.markdown(f"**Retrieval check** ({retriever.description}): the passages each rule's query retrieves.")
check_rows = []
for rule_id, query in RULE_QUERIES.items():
    hits = ui.related_guidance(retriever, f"{kb_fp}|{retriever.method}", query, tuple(PER_DOC.items()))
    check_rows.append({
        "Rule": rule_id,
        "Retrieved passages (score)": ", ".join(f"{h.passage.citation} ({h.score:.2f})" for h in hits),
    })
st.dataframe(pd.DataFrame(check_rows), hide_index=True, use_container_width=True)

st.header("5. Implementation details")
st.dataframe(
    pd.DataFrame([
        ("app.py", "Sign-in gate and page navigation"),
        ("views/review.py", "Main page: G2B, G2C and Reason & justification tabs"),
        ("govlens/engine.py", "Data normalisation and the G2B, G2C and REASON rules"),
        ("govlens/knowledge.py", "Knowledge-base parser, embeddings, local vector store, keyword fallback"),
        ("govlens/rag.py", "Retrieval queries, explanation prompt, citation validation"),
        ("govlens/justification.py", "Price bands, justification prompt and schema, escalation, caching"),
        ("govlens/ui.py", "Shared page helpers: models, API key, retriever, reviewer notes"),
        ("knowledge_base/*.md", "Curated Governance Guide, Data Glossary and rule specification"),
        ("scripts/build_glossary_kb.py", "Rebuilds the glossary passages from the official .xlsx"),
        ("tests/", "Automated tests for rules, retrieval, citation checks, the AI screen and the pages"),
    ], columns=["Module", "Responsibility"]),
    hide_index=True, use_container_width=True,
)
st.markdown(
    f"**LLM settings.** Chat model `{ui.CHAT_MODEL}` via the OpenAI Responses API; temperature 0 and a "
    "strict JSON schema for the AI screen; bounded output length; `store=False` on every request. "
    f"Embeddings use `{ui.EMBEDDING_MODEL}`. Both are fixed in code.\n\n"
    "**Prompt-engineering techniques.** Role and task framing; delimited JSON inputs; explicit output "
    "structure (headings for explanations, JSON schema for the screen); worked examples of "
    "function-versus-marketing reasoning; instructions to treat buyer and seller text as untrusted "
    "data; and a two-stage chain in each use case: retrieval then grounded generation then citation "
    "check (use case 1), and LLM judgement then deterministic escalation (use case 2).\n\n"
    "**Testing.** Automated tests cover the rule edge cases (thresholds, agency separation, cancelled "
    "and welfare exclusions, no double counting), retrieval of the right guidance for each rule, "
    "vector-store caching, rejection of invented citations, price-band and escalation maths, the "
    "JSON-schema contract, the sign-in gate and the page layout."
)

st.header("6. Limitations")
st.markdown(
    "- Masked historical exports stand in for a real-time QB feed; there is no live integration.\n"
    "- Rule thresholds are screening heuristics. The 1 April / 1 October reset dates are a GovLens "
    "assumption; the Governance Guide states the \\$6k limit but not the reset dates.\n"
    "- The REASON rule is deliberately broad and will raise false alarms.\n"
    "- Product categories are broad marketplace labels, so price bands can compare dissimilar items.\n"
    "- LLM judgements can be wrong (for example, inferring a purpose the reason does not state). They are "
    "labelled as AI-suggested and require human review.\n"
    "- No user roles, agency access control or audit trail; a single hardcoded login protects the prototype."
)
