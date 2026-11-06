"""Methodology page: data flows, implementation, rules, data health, knowledge base, one flowchart per use case."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from govlens import evaluation as ev
from govlens import justification as js
from govlens import ui
from govlens.crew import AGENT_SKILLS, CREW_SKILLS
from govlens.demo import load_masked_sample
from govlens.engine import Settings, analyse
from govlens.flowcharts import FLOW_OVERVIEW, FLOW_UC1, FLOW_UC2
from govlens.knowledge import load_knowledge_base
from govlens.rag import PER_DOC, RULE_QUERIES, SYSTEM_INSTRUCTIONS
from govlens.skills import list_skills


@st.cache_data(show_spinner=False)
def _justification_tiers() -> pd.DataFrame:
    _, orders, detail, _ = analyse(*load_masked_sample(), Settings())
    items = js.add_price_bands(js.build_items(orders, detail))
    eligible = js.eligible_carts(items)
    results = js.cached_results(items, eligible["Cart_ID"].tolist(), ui.CHAT_MODEL, js.ScreenCache())
    return pd.DataFrame([
        {"cart_id": c, "govlens_tier": js.combined_tier(items, c, str(r), results.get(c))["Tier"]}
        for c, r in zip(eligible["Cart_ID"], eligible["Reason_For_Purchase"])
    ])


@st.cache_data(show_spinner=False)
def _sample_quality() -> dict:
    try:
        return analyse(*load_masked_sample(), Settings())[3]
    except FileNotFoundError:
        return {}


st.title("Methodology")
st.markdown(
    "QB GovLens combines **deterministic rules** (which decide the split-purchase flags), an **agent crew** "
    "built with CrewAI that investigates a flagged case with read-only tools and explains it with verified "
    "citations from official QB guidance (retrieval-augmented generation), and an **LLM judgement step** that "
    "rates purchase justification with cited guidance, bounded by deterministic price logic and a rule minimum. "
    "The instructions each model follows are kept as **skills** (SKILL.md files). Colour key in every "
    "flowchart: blue = Python, purple = LLM or embeddings, yellow = administrator action, green = output."
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
    "Each case opens with a chart for the question the rule leaves to the reviewer: for G2B, spend summed "
    "across the reset with orders coloured where the same category was bought on both sides; for G2C, one "
    "row per buyer across the half-year, coloured by seller, so same-day buying stands out.\n\n"
    "**Retrieval.** When the administrator clicks *Review and explain this case*, a natural-language "
    "query is built from the rule's definition, the case pattern and any shared categories. The query is "
    "embedded and compared with every passage by cosine similarity; the top "
    f"{PER_DOC['GG']} Governance Guide, {PER_DOC['DG']} Data Glossary and {PER_DOC['RS']} rule-spec "
    "passages are kept. Without an API key, a keyword retriever is used and the sidebar says so.\n\n"
    "**Agent crew (CrewAI).** Three agents run in sequence with `gpt-4o-mini` at temperature 0. The "
    "**evidence analyst** queries the case with read-only tools and lists the facts that support or weaken "
    "a single-need reading (for example, one buyer placing ten orders with one seller on one day). The "
    "**guidance researcher** searches the knowledge base for passages that bear on those facts, on top of "
    "the passages retrieved above. The **report writer** turns both into a five-part report: signal, "
    "transaction evidence, relevant guidance, possible legitimate explanations, checks for the "
    "administrator. Why a crew rather than one prompt: the single-call explanation can only be sent the "
    "first 16 orders of a case, while G2C cases in the sample have up to 79 orders; the analyst's tools "
    "summarise all of them, and every number the analyst uses comes from Python.\n\n"
    "**Citation guardrail (Python, outside the LLM).** The writer's task carries a CrewAI guardrail: a Python "
    "function that accepts the report only if every passage it cites was retrieved in this run and every "
    "`[QB:order]` belongs to the case. If not, the writer is told what failed and tries again (at most twice). "
    "The same check runs once more after the crew. If the crew fails, GovLens falls back to a single AI "
    "call (same citation check), and then to a local evidence-only narrative. The tool calls, the "
    "analyst's facts, the researcher's passages and all retrieved passages are shown under the report.\n\n"
    "**Ask about this case.** After a review, the administrator can ask follow-up questions (for example, "
    "*did any buyer order from the same seller on the same day?*). One agent answers with the same four "
    "tools and the same guardrail; questions and answers are included in the downloaded review record."
)
with st.expander("System instructions used for the explanation"):
    st.code(SYSTEM_INSTRUCTIONS, language="text")

st.header("3. Use case 2: purchase justification (one tab)")
st.graphviz_chart(FLOW_UC2, use_container_width=True)
st.markdown(
    "Each cart gets **one tier**, built from three inputs, with a *Why* column naming what drove it.\n\n"
    "**Reason check (Python; Guide p.20, anomalies in reasons for purchase).** The REASON rule reads the "
    "reason text and records whether it is vague (e.g. 'QB2025', 'QB buy', fewer than two meaningful words "
    "without a purpose hashtag) and whether it contains approval wording (offline, email, refer, approval), "
    "which can suggest approval sought outside QB. Both findings are passed to the AI. Approval wording also "
    "sets a **minimum of Medium** for the cart, so the AI cannot rate it away.\n\n"
    "**AI assessment (LLM with retrieval; Guide p.22 requirement for purchase).** For each cart, a query "
    "built from the reason and product categories is embedded and matched against the knowledge base; "
    f"the top {js.GUIDANCE_PER_DOC['GG']} Governance Guide passages and top {js.GUIDANCE_PER_DOC['RS']} "
    "rule-spec passage are sent with the cart. The model judges each item's core function against the "
    "stated reason (ignoring marketing themes but not luxury brand tier) and assigns a base level from Very "
    "Low to Very High, or Uncertain. It must not invent a purpose the reason does not state: a reason with no "
    "operational context is a documentation gap (Medium for everyday items, High for specialised or costly "
    "items, Very High only for items with no conceivable use); agency purpose hashtags count as a stated "
    "purpose. The response must match a strict JSON schema whose citation field only accepts the passages "
    "supplied; GovLens also rejects any assessment that cites nothing or cites an unknown passage. Carts with "
    "more than 25 items are sent in parts.\n\n"
    "**Price escalation (Python; Guide p.24 price reasonableness).** Unit price after discount "
    "(`Amount_After_Discount / Qty`) is compared with items from *other* carts in the same "
    "`Product_Category` across all agencies. With more than 5 comparison records, an item between the "
    "90th percentile and the maximum is escalated by one tier and an item above the maximum by two tiers, "
    "capped at Very High. Price never lowers a level and Uncertain items are not escalated. Price bands "
    "are deliberately **not** sent to the model, so the arithmetic is transparent and testable.\n\n"
    "**Combining.** The cart takes its highest item level after price escalation, raised to Medium if the "
    "reason has approval wording. Until a cart has an AI result its tier is provisional and rule-only "
    "(Medium for approval wording, Low for a vague reason). AI results for the masked sample are "
    "precomputed and shipped with the app (`scripts/precompute_ai_screen.py`), so viewers see them "
    "without triggering API calls."
)
st.dataframe(
    pd.DataFrame({
        "Five-level result": ["Very High", "High", "Medium", "Low", "Very Low", "Uncertain"],
        "Display tier": [js.DISPLAY_TIER[k] for k in ["Very High", "High", "Medium", "Low", "Very Low", "Uncertain"]],
    }),
    hide_index=True,
)
with st.expander("Purchase-justification prompt"):
    st.code(js.SYSTEM_PROMPT, language="text")
with st.expander("Required JSON output schema"):
    st.json(js.OUTPUT_SCHEMA)

st.header("4. Agents, tools and skills")
st.markdown(
    "**Tools** are Python functions the agents can call. All are read-only, and none can change a case, a "
    "tier or a score. Buyers appear only as *Buyer A, Buyer B...* (ordered by spend), never by e-mail."
)
st.dataframe(
    pd.DataFrame([
        ("case_overview", "Evidence analyst, Q&A", "Rule, priority, score breakdown, dates, totals, buyers with totals"),
        ("list_orders", "Evidence analyst, Q&A", "Up to 40 orders, filtered by buyer, seller, category, side of the reset or dates"),
        ("summarise_orders", "Evidence analyst, Q&A", "Totals and counts for all orders grouped by buyer, seller, date, week, month, category or side"),
        ("search_guidance", "Guidance researcher, Q&A", "Searches the GG, DG and RS passages; returns citation IDs"),
    ], columns=["Tool", "Used by", "Returns"]),
    hide_index=True, use_container_width=True,
)
st.markdown(
    "**Skills** are the instructions each model follows, kept as `skills/<name>/SKILL.md` files in the open "
    "Agent Skills format (a name and description, then Markdown instructions). Skills shape how an agent "
    "works; tools let it act. CrewAI normally shows an agent only a skill's description and lets it decide "
    "whether to load the rest; GovLens loads every skill in full, so each run follows the same instructions. "
    "The citation skill is attached to the whole crew; the others to one agent each. The "
    "purchase-justification screen is a single structured call, not a crew, and reads its skill file "
    "directly as its system prompt."
)
_owners = {name: role for role, names in AGENT_SKILLS.items() for name in names}
_owners.update({name: "whole crew" for name in CREW_SKILLS})
_owners["govlens-purchase-justification"] = "purchase-justification screen"
_roles = {"analyst": "Evidence analyst", "researcher": "Guidance researcher", "writer": "Report writer",
          "qa": "Case Q&A agent"}
_skills = list_skills()
st.dataframe(
    pd.DataFrame([
        {"Skill": s.name, "Attached to": _roles.get(_owners.get(s.name, ""), _owners.get(s.name, "")),
         "Version": s.version, "What it is for": s.description}
        for s in _skills
    ]),
    hide_index=True, use_container_width=True,
)
for skill in _skills:
    if skill.name == "govlens-purchase-justification":
        continue  # shown in section 3
    with st.expander(f"{skill.name}/SKILL.md"):
        st.markdown(ui.md(skill.body))

st.header("5. Evaluation")
st.markdown(
    "**Retrieval** is checked in section 6: each rule's query should retrieve the matching Governance Guide "
    "check. **Case reviews** are evaluated with `scripts/evaluate_reviews.py`, which runs the crew and the "
    "single-call explanation on every G2B and G2C case and records whether each passed the citation check, "
    "how long it took and how many dollar figures in the text cannot be traced to the data the model was "
    "given (a proxy for invented numbers). It also writes both reports as *Report A* and *Report B* in random "
    "order for blind rating. **Purchase justification** is evaluated with `scripts/evaluate_justification.py`: "
    "a reviewer gives their own tier for 12 carts sampled across tiers, without seeing GovLens's tier, and "
    "agreement is computed."
)
runs = ev.read_csv(ev.REVIEW_RUNS)
if runs is not None and not runs.empty:
    numeric = runs.assign(**{c: pd.to_numeric(runs[c], errors="coerce") for c in
                             ("seconds", "untraceable_amounts", "total_tokens", "tool_calls")},
                          passed=runs["passed"].str.lower().eq("true"))
    summary = numeric.groupby("engine").agg(
        cases=("case_id", "nunique"), passed_citation_check=("passed", "mean"),
        median_seconds=("seconds", "median"), untraceable_dollar_figures=("untraceable_amounts", "sum"),
        median_tool_calls=("tool_calls", "median"),
    ).reset_index()
    summary["passed_citation_check"] = (summary["passed_citation_check"] * 100).round(0).astype(int).astype(str) + "%"
    st.markdown("**Case reviews: automatic checks**")
    st.dataframe(summary.rename(columns={"engine": "Engine"}), hide_index=True, use_container_width=True)
    labels = ev.read_csv(ev.REVIEW_LABELS)
    if labels is not None and (labels.get("useful_1_to_5", pd.Series(dtype=str)) != "").any():
        rated = labels[labels["useful_1_to_5"] != ""].merge(
            runs[["case_id", "engine", "blind_label"]].rename(columns={"blind_label": "report"}), on=["case_id", "report"])
        rated["useful"] = pd.to_numeric(rated["useful_1_to_5"], errors="coerce")
        rated["facts_correct"] = rated["facts_correct_Y_N"].str.upper().eq("Y")
        st.markdown("**Case reviews: blind ratings by a QB reviewer**")
        st.dataframe(rated.groupby("engine").agg(reports=("case_id", "size"), facts_correct=("facts_correct", "mean"),
                                                 mean_usefulness=("useful", "mean")).round(2).reset_index(),
                     hide_index=True, use_container_width=True)
else:
    st.info("Case-review evaluation has not been run yet: `python scripts/evaluate_reviews.py` (needs an API key).")
jl = ev.read_csv(ev.JUSTIFICATION_LABELS)
if jl is not None and (jl.get("your_tier", pd.Series(dtype=str)).isin(ev.TIERS)).any():
    ai_tiers = _justification_tiers()
    result = ev.agreement(jl.merge(ai_tiers, on="cart_id", how="left"))
    st.markdown(
        f"**Purchase justification: agreement with a QB reviewer** ({result['labelled']} carts, blind). "
        f"Exact agreement {result['exact_agreement']:.0%}; GovLens higher than the reviewer on "
        f"{result['govlens_higher']}, lower on {result['govlens_lower']}."
    )
    st.dataframe(pd.DataFrame(result["confusion"]).T.rename_axis("Reviewer tier (rows) vs GovLens tier (columns)"),
                 use_container_width=True)
else:
    st.info("Purchase-justification labels are not filled in yet (`evaluation/justification_labels.csv`).")

st.header("6. Data health, knowledge base and retrieval check")
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

st.header("7. Implementation details")
st.dataframe(
    pd.DataFrame([
        ("app.py", "Sign-in gate and page navigation"),
        ("views/review.py", "Main page: G2B, G2C and Purchase justification tabs"),
        ("govlens/engine.py", "Data normalisation and the G2B, G2C and REASON rules"),
        ("govlens/knowledge.py", "Knowledge-base parser, embeddings, local vector store, keyword fallback"),
        ("govlens/rag.py", "Retrieval queries, single-call explanation prompt, citation validation"),
        ("govlens/crew.py", "CrewAI review crew and Q&A agent, tools, citation guardrail, telemetry off"),
        ("govlens/casefacts.py", "Read-only views of one case for the agent tools (buyers as Buyer A, B...)"),
        ("govlens/skills.py", "Reads the SKILL.md files; loads them into CrewAI agents"),
        ("skills/*/SKILL.md", "The six skills: instructions for each agent and for the justification screen"),
        ("govlens/charts.py", "G2B and G2C charts; the price comparison table"),
        ("govlens/evaluation.py, scripts/evaluate_*.py", "Evaluation of case reviews and of the justification tier"),
        ("govlens/justification.py", "Price bands, justification prompt and schema, combined tier, results cache"),
        ("scripts/precompute_ai_screen.py", "Runs the AI assessment for the sample and saves results shipped with the app"),
        ("govlens/ui.py", "Shared page helpers: models, API key, retriever, reviewer notes"),
        ("knowledge_base/*.md", "Curated Governance Guide, Data Glossary and rule specification"),
        ("scripts/build_glossary_kb.py", "Rebuilds the glossary passages from the official .xlsx"),
        ("tests/", "Automated tests for rules, retrieval, citation checks, the AI screen, the crew, charts and pages"),
    ], columns=["Module", "Responsibility"]),
    hide_index=True, use_container_width=True,
)
st.markdown(
    f"**LLM settings.** Chat model `{ui.CHAT_MODEL}`: the AI screen and the single-call explanation use the "
    "OpenAI Responses API with `store=False`; the crew uses CrewAI's OpenAI connector (Chat Completions, which "
    "OpenAI does not store by default). Temperature 0 throughout; strict JSON schema for the AI screen. "
    "CrewAI's telemetry and tracing are switched off, and the task outputs it keeps on disk are cleared "
    "after each run. "
    f"Embeddings use `{ui.EMBEDDING_MODEL}`. Both are fixed in code.\n\n"
    "**Prompt-engineering techniques.** Role and task framing; delimited JSON inputs; explicit output "
    "structure (headings for explanations, JSON schema for the screen); worked examples of "
    "function-versus-marketing reasoning; instructions to treat buyer and seller text as untrusted "
    "data; role-specific agents with their own skills and tools; and a chain in each use case: retrieval, "
    "tool-based analysis, grounded writing and a Python citation guardrail (use case 1), and retrieval, "
    "LLM judgement with citations, then deterministic escalation and rule minimum (use case 2).\n\n"
    "**Testing.** Automated tests cover the rule edge cases (thresholds, agency separation, cancelled "
    "and welfare exclusions, no double counting), retrieval of the right guidance for each rule, "
    "vector-store caching, rejection of invented citations, price-band and escalation maths, the "
    "JSON-schema and citation contract, the combined tier and its minimum, the sign-in gate and the page layout. "
    "The crew is tested offline with a scripted model, so CrewAI really parses its tool calls, runs the tools, "
    "loads the skills and applies the guardrail without an API key."
)

st.header("8. Limitations")
st.markdown(
    "- Masked historical exports stand in for a real-time QB feed; there is no live integration.\n"
    "- Rule thresholds are screening heuristics. The 1 April / 1 October reset dates are a GovLens "
    "assumption; the Governance Guide states the \\$6k limit but not the reset dates.\n"
    "- The REASON rule is deliberately broad and will raise false alarms.\n"
    "- Product categories are broad marketplace labels, so price bands can compare dissimilar items.\n"
    "- LLM judgements can be wrong (for example, inferring a purpose the reason does not state). They are "
    "shown with the reasons behind each tier and require human review.\n"
    "- The crew makes several model calls per review (about 20 to 60 seconds) and adds CrewAI and its "
    "dependencies to the app. The citation guardrail checks that sources are real and relevant to the run, "
    "not that every sentence is a fair reading of them.\n"
    "- No user roles, agency access control or audit trail; a single hardcoded login protects the prototype."
)
