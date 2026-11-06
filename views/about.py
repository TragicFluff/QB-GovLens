"""About Us page: project scope, objectives, data sources and features."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from govlens.demo import load_masked_sample
from govlens.knowledge import load_knowledge_base


@st.cache_data(show_spinner=False)
def _sample_counts() -> dict[str, int]:
    try:
        invoices, carts, items = load_masked_sample()
    except FileNotFoundError:
        return {}
    return {
        "invoices": len(invoices), "carts": len(carts), "items": len(items),
        "agencies": invoices["Agency_Code"].nunique() if "Agency_Code" in invoices else 0,
    }


st.title("About Us")
st.markdown(
    "**QB GovLens** is a governance-by-design prototype for **QuickBuy@SGov (QB)**, the Singapore "
    "Government's procure-to-pay platform for small value purchases from e-commerce marketplaces. "
    "It is built from the perspective of QB's own product owner: someone accountable both for "
    "catching governance risk and for the purchasing experience QB promises its users."
)

st.header("Problem statement")
st.markdown(
    "QB already captures every purchase in structured form, and agency administrators can download "
    "it from the QB Admin Portal as CSV files. The official *QB Admin Portal Governance Guide* then "
    "suggests checks that administrators carry out by hand, with filters, pivot tables and lookups, "
    "outside the platform. Governance therefore happens **after the fact**, depends on someone "
    "remembering to run it, and gives the reviewer no explanation of *why* a purchase looks the way "
    "it does or which guidance applies."
)

st.header("Objectives")
st.markdown(
    "1. **Design governance into the workflow:** run the Governance Guide's checks automatically on "
    "QB data and let an administrator review any flagged purchase with one click.\n"
    "2. **Explain, with sources:** an agent crew investigates each flagged pattern in the case data and "
    "explains it with citations to the official guide and glossary, so the reviewer can verify every claim, "
    "then answers the reviewer's follow-up questions.\n"
    "3. **Assess purchase justification at scale:** use an LLM to judge whether each item fits the "
    "stated reason for purchase, combined with an objective price comparison.\n"
    "4. **Keep humans in charge and buyers unaffected:** every output is a review aid, not a "
    "finding, and nothing adds a step or delay to the purchase itself."
)

st.header("Project scope")
col_in, col_out = st.columns(2)
with col_in:
    st.markdown("**In scope**")
    st.markdown(
        "- Users: agency QB administrators and approving officers\n"
        "- Data: QB-native Carts, Invoices and InvoiceItems exports (masked)\n"
        "- Governance Guide checks covered: *Split purchases* (rules G2B and G2C), "
        "*Anomalies in reasons for purchase* (rule REASON), and *requirement for purchase / price "
        "reasonableness* (AI justification screen)\n"
        "- Two use cases (below), delivered as three tabs: G2B, G2C and Purchase justification"
    )
with col_out:
    st.markdown("**Out of scope for this prototype**")
    st.markdown(
        "- Live integration with the QB Admin Portal (masked exports stand in for a real-time feed)\n"
        "- Claims data and cross-channel checks (e.g. double claims)\n"
        "- Splitting under an agency's own per-cart limit\n"
        "- User roles, agency access control and an audit trail\n"
        "- Any automated decision or action on a buyer"
    )

st.header("Use cases")
uc1, uc2 = st.columns(2)
with uc1:
    st.subheader("1. Split-purchase review with a cited explanation")
    st.markdown(
        "Two deterministic rules screen every purchase, each in its own tab. **G2B** looks for one "
        "officer's spend across the six-monthly reset of the \\$6,000 limit; **G2C** looks for several "
        "buyers in one cost centre buying the same category in a half-year. An administrator opens a "
        "flagged case, sees a chart of the pattern and clicks **Review and explain**. A three-agent crew "
        "(evidence analyst, guidance researcher, report writer) queries the case with read-only tools, "
        "searches the official Governance Guide, Data Glossary and GovLens rule specification, and writes "
        "a report in which every citation is checked in Python. The administrator can then **ask "
        "follow-up questions** about the case."
    )
with uc2:
    st.subheader("2. Purchase justification")
    st.markdown(
        "Each cart gets **one tier** for whether its reason for purchase justifies what was bought. A rule "
        "checks the reason text for vague wording and approval wording; an LLM, given that check and "
        "retrieved guidance to cite, judges whether each item's core function fits the stated reason; and "
        "GovLens raises the tier for items priced above the category's 90th percentile. A **Why** column "
        "names what drove each tier, and approval wording always means at least Medium."
    )

st.header("Data sources")
counts = _sample_counts()
kb = load_knowledge_base()
kb_counts = {d: sum(p.doc == d for p in kb) for d in ("GG", "DG", "RS")}
sources = pd.DataFrame([
    {
        "Source": "Masked QB Admin Portal exports (Carts, Invoices, InvoiceItems)",
        "Owner": "QuickBuy@SGov",
        "Used for": "Rule screening, price bands, AI justification screen",
        "Size in app": (
            f"{counts.get('carts', 0):,} carts, {counts.get('invoices', 0):,} invoices, "
            f"{counts.get('items', 0):,} items" if counts else "not loaded"
        ),
    },
    {
        "Source": "QB Admin Portal Governance Guide for Agencies",
        "Owner": "Ministry of Finance and GovTech",
        "Used for": "Knowledge base (cited as GG): suggested governance checks, data interpretation",
        "Size in app": f"{kb_counts['GG']} curated passages",
    },
    {
        "Source": "Data Glossary of QB Admin Portal Data (Headers), updated 12 Dec 2025",
        "Owner": "Ministry of Finance and GovTech",
        "Used for": "Knowledge base (cited as DG): field definitions, verbatim",
        "Size in app": f"{kb_counts['DG']} passages",
    },
    {
        "Source": "QB GovLens rule specification",
        "Owner": "This project (tool documentation, not policy)",
        "Used for": "Knowledge base (cited as RS): how each rule and the AI screen work",
        "Size in app": f"{kb_counts['RS']} passages",
    },
])
st.markdown(
    "| " + " | ".join(sources.columns) + " |\n|" + "---|" * len(sources.columns) + "\n"
    + "\n".join("| " + " | ".join(str(v) for v in row) + " |" for row in sources.itertuples(index=False))
)
st.caption(
    "Purchase data is masked: buyer and approver e-mails are hashed and agency names are obfuscated. "
    "No live or personal data is used."
)

st.header("Features")
st.markdown(
    "| Where | Feature |\n|---|---|\n"
    "| Governance review › G2B and G2C tabs | Flagged cases by priority with score breakdown, CSV export; open a "
    "case to see a chart of the pattern, its orders and items; one-click **Review and explain** by an agent crew, "
    "with the tool calls, retrieved passages and similarity scores; **Ask about this case** follow-up questions; "
    "reviewer disposition and notes, JSON export |\n"
    "| Governance review › Purchase justification | One row per cart with a single tier and the reasons for it, "
    "filters, CSV export; AI results shipped with the app; cart detail with the AI assessment and its cited "
    "guidance, price working, the dearest items each price band compares with, item table, reviewer notes and "
    "JSON export |\n"
    "| Methodology | Flowcharts, the agents, tools and skills, evaluation results, prompts, data coverage, the full "
    "knowledge-base index and a retrieval check per rule |\n"
    "| Sidebar | Data source (masked sample or upload) and detection settings: days around the reset, cost-centre "
    "screening amount, shared reason words |"
)

st.header("Guardrails")
st.markdown(
    "- The LLM **never decides** which purchases enter the governance queue; rule tiers and scores are computed in Python.\n"
    "- The agents' tools are read-only and show buyers only as Buyer A, Buyer B...; no agent can change a case.\n"
    "- AI explanations and answers are discarded unless every policy citation matches a passage retrieved in "
    "that run and every order cited belongs to the case (checked in Python, not by the model).\n"
    "- Purchase reasons and item descriptions are treated as untrusted text, never as instructions.\n"
    "- Language stays non-accusatory: patterns can have legitimate explanations.\n"
    "- OpenAI requests are sent only after an administrator clicks; CrewAI telemetry and tracing are off."
)

st.header("Project")
st.markdown(
    "Individual capstone project (Project Type 2), AI Champions Bootcamp. "
    "Built with Python, Streamlit, CrewAI, pandas, NumPy, Altair and the OpenAI API (gpt-4o-mini and "
    "text-embedding-3-small)."
)
