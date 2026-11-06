"""Graphviz (DOT) flowcharts for the Methodology page (colour key is explained on the page).

Colour key: blue = deterministic Python step, purple = LLM / embedding call,
yellow = administrator action, green = output shown to the administrator,
grey cylinder = data store, white diamond = decision.
"""

from __future__ import annotations

_STYLE = """
  graph [bgcolor="white", rankdir=TB, fontname="Helvetica", fontsize=11, nodesep=0.35, ranksep=0.38, pad=0.3];
  node  [fontname="Helvetica", fontsize=10.5, shape=box, style="rounded,filled", color="#5b6b7f", fillcolor="#e8f0fb", margin="0.16,0.07"];
  edge  [fontname="Helvetica", fontsize=9.5, color="#5b6b7f", fontcolor="#3a4656", arrowsize=0.7];
"""

ADMIN = 'fillcolor="#fff4cc", color="#b08900"'
AI = 'fillcolor="#efe6fb", color="#7a4fb5"'
OUT = 'fillcolor="#e3f5e8", color="#2f8a4b"'
STORE = 'shape=cylinder, style=filled, fillcolor="#eef0f2", color="#6b7785"'
DECISION = 'shape=diamond, style=filled, fillcolor="white", color="#5b6b7f", fontsize=9.5'

FLOW_OVERVIEW = f"""digraph overview {{
{_STYLE}
  rankdir=TB;
  subgraph cluster_data {{
    label="Purchase data"; fontsize=11; style="rounded"; color="#c8ced6";
    exports [label="Masked QB Admin Portal exports\\nCarts · Invoices · InvoiceItems", {STORE}];
    norm [label="Normalise and join\\nRef_Cart_ID = Cart_ID\\nParent_Invoice_ID = Invoice_ID\\napproved, non-cancelled carts\\nevent date = Order_Date"];
    exports -> norm;
  }}
  subgraph cluster_kb {{
    label="Knowledge base (built in)"; fontsize=11; style="rounded"; color="#c8ced6";
    docs [label="Governance Guide (GG)\\nData Glossary (DG)\\nGovLens rule spec (RS)\\ncurated markdown", {STORE}];
    chunk [label="One passage per\\n## [ID] section"];
    embed [label="Embed passages\\ntext-embedding-3-small", {AI}];
    vs [label="Local vector store\\n.cache/*.npz", {STORE}];
    docs -> chunk -> embed -> vs;
  }}
  split [label="Split-purchase rules\\nG2B · G2C"];
  reason [label="Reason check (REASON)\\n+ price bands"];
  aiscreen [label="AI assessment\\n(cites retrieved guidance)", {AI}];
  crew [label="Agent crew (CrewAI)\\nanalyst · researcher · writer\\n+ follow-up Q&A agent", {AI}];
  skills [label="Skills\\n(SKILL.md instructions)", {STORE}];
  uc1 [label="Use case 1: split-purchase review\\nG2B and G2C tabs\\ncase list + cited explanation", {OUT}];
  uc2 [label="Use case 2: purchase justification\\none combined tier per cart\\nwith the reasons for it", {OUT}];
  norm -> split -> crew -> uc1;
  skills -> crew [style=dashed];
  skills -> aiscreen [style=dashed];
  norm -> reason -> uc2;
  norm -> aiscreen -> uc2;
  vs -> crew [label="retrieve", style=dashed];
  vs -> aiscreen [label="retrieve", style=dashed];
}}"""

FLOW_UC1 = f"""digraph uc1 {{
{_STYLE}
  start [label="Admin opens the G2B or G2C tab\\nand chooses the financial years", {ADMIN}];
  rules [label="Rules have already scored all purchases\\nG2B: one officer's spend across the 1 Apr / 1 Oct reset\\nG2C: several buyers, same cost centre and category\\n(tiers and scores computed in Python, never by the LLM)"];
  list [label="List of flagged cases\\n(priority, score, amounts, shared categories and reasons)\\nCSV download", {OUT}];
  open [label="Admin opens a case:\\nevidence, chart, orders and items", {ADMIN}];
  click [label="Admin clicks \\"Review and explain this case\\"", {ADMIN}];
  search [label="Retrieve passages for the rule\\nembed query · top 3 GG + 2 DG + 1 RS"];
  vs [label="Local vector store", {STORE}];
  skills [label="Skills (SKILL.md files)\\nevidence analysis · guidance research\\ncase report · citations · case Q&A", {STORE}];
  key [label="OpenAI key set?", {DECISION}];
  crewok [label="CrewAI\\ninstalled?", {DECISION}];
  subgraph cluster_crew {{
    label="Agent crew (CrewAI, sequential, gpt-4o-mini, temperature 0)"; fontsize=10.5; style="rounded,dashed"; color="#7a4fb5";
    analyst [label="Evidence analyst\\ntools: case_overview · list_orders ·\\nsummarise_orders (all orders, buyers as A, B…)", {AI}];
    researcher [label="Guidance researcher\\ntool: search_guidance\\n(GG · DG · RS)", {AI}];
    writer [label="Report writer\\nno tools · five headings ·\\nnon-accusatory", {AI}];
    guard [label="Task guardrail (Python):\\ncitations retrieved in this run?\\norders in this case?\\nno → writer retries (max 2)"];
    analyst -> researcher -> writer -> guard;
  }}
  gate [label="Final citation check\\n(Python, after the crew)", {DECISION}];
  single [label="Single gpt-4o-mini call\\ncase + first 16 orders + passages\\nstore=False", {AI}];
  valid [label="Every citation is one of\\nthe retrieved passages?", {DECISION}];
  local [label="Local narrative from evidence\\n(cites transaction IDs only)"];
  report [label="Review report + tool-call trace +\\nretrieved passages (check every citation)", {OUT}];
  ask [label="Admin asks a follow-up question\\n\\"Ask about this case\\"", {ADMIN}];
  qa [label="Case Q&A agent\\nall four tools · same guardrail", {AI}];
  answer [label="Cited answer kept with the review", {OUT}];
  notes [label="Admin records disposition and notes\\nDownload review (JSON) incl. Q&A", {ADMIN}];

  start -> rules -> list -> open -> click -> search;
  vs -> search [style=dashed];
  search -> key;
  key -> local [label="no"];
  key -> crewok [label="yes"];
  crewok -> analyst [label="yes"];
  crewok -> single [label="no"];
  skills -> analyst [style=dashed];
  skills -> qa [style=dashed];
  guard -> gate;
  gate -> report [label="pass"];
  gate -> single [label="fail or error"];
  single -> valid;
  valid -> report [label="yes"];
  valid -> local [label="no: discard\\nAI text"];
  local -> report;
  report -> ask -> qa -> answer;
  answer -> notes;
  report -> notes [style=dashed];
}}"""

FLOW_UC2 = f"""digraph uc2 {{
{_STYLE}
  start [label="Admin opens the Purchase justification tab", {ADMIN}];
  scope [label="Approved, non-cancelled carts\\n(selected agency and financial years)"];
  rule [label="Reason check (Python) on the reason text\\nvague? (e.g. QB2025)\\napproval wording? (offline / email / refer / approval)"];
  bundle [label="AI results shipped with the app\\n(precomputed, keyed by cart data,\\nmodel and prompt version)", {STORE}];
  have [label="AI result for\\nthis cart?", {DECISION}];
  click [label="Admin clicks \\"Assess N carts\\"\\n(only for carts without a result)", {ADMIN}];
  query [label="Retrieval query from reason + categories\\n→ embed → top 3 GG + top 1 RS passages"];
  vs [label="Local vector store", {STORE}];
  payload [label="Payload per cart: reason, pre-checks, items\\n(qty, prices; no price bands), guidance passages\\nchunks of ≤ 25 items"];
  llm [label="gpt-4o-mini with the purchase-justification skill\\nno invented purpose · label-only reason = gap\\nBASE level per item · cites guidance\\nstrict JSON schema · temperature 0", {AI}];
  check [label="Validate: every item returned, allowed levels,\\ncitations only from supplied passages"];
  bands [label="Unit price after discount vs. OTHER carts' items\\nin the same Product_Category (all agencies)"];
  esc [label="More than 5 records: 90th pct–max +1 tier,\\nabove max +2, cap Very High\\n→ cart level = highest item level"];
  floor [label="Combine: never below Medium\\nif approval wording found"];
  prov [label="Provisional rule-only tier\\napproval wording → Medium\\nvague → Low"];
  table [label="One row per cart: tier + Why\\n(reason check · AI summary · price)\\nfilters · CSV download", {OUT}];
  detail [label="Cart detail: AI assessment with citations,\\nprice working, items, cited passages,\\nreviewer notes · JSON download", {OUT}];

  start -> scope;
  scope -> rule;
  scope -> have;
  bundle -> have [style=dashed];
  have -> esc [label="yes"];
  have -> prov [label="no"];
  prov -> click [style=dashed];
  click -> query;
  vs -> query [style=dashed];
  query -> payload;
  rule -> payload [label="pre-checks", style=dashed];
  payload -> llm -> check -> esc;
  bands -> esc;
  scope -> bands;
  esc -> floor;
  rule -> floor [label="approval wording", style=dashed];
  floor -> table;
  prov -> table;
  table -> detail;
}}"""

FLOWCHARTS = {"overview": FLOW_OVERVIEW, "uc1": FLOW_UC1, "uc2": FLOW_UC2}
