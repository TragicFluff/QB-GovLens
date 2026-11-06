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
  reason [label="Reason rule (REASON)\\n+ price bands"];
  aiscreen [label="AI justification screen", {AI}];
  uc1 [label="Use case 1: split-purchase review\\nG2B and G2C tabs\\ncase list + cited explanation", {OUT}];
  uc2 [label="Use case 2: reason & justification\\nrule flag and AI-suggested tier\\nside by side", {OUT}];
  norm -> split -> uc1;
  norm -> reason -> uc2;
  norm -> aiscreen -> uc2;
  vs -> uc1 [label="retrieve", style=dashed];
  vs -> uc2 [label="related guidance", style=dashed];
}}"""

FLOW_UC1 = f"""digraph uc1 {{
{_STYLE}
  start [label="Admin opens the G2B or G2C tab\\nand chooses the financial years", {ADMIN}];
  rules [label="Rules have already scored all purchases\\nG2B: one officer's spend across the 1 Apr / 1 Oct reset\\nG2C: several buyers, same cost centre and category\\n(tiers and scores computed in Python, never by the LLM)"];
  list [label="List of flagged cases\\n(priority, score, amounts, shared categories and reasons)\\nCSV download", {OUT}];
  open [label="Admin opens a case:\\nevidence, orders and items", {ADMIN}];
  click [label="Admin clicks \\"Review and explain this case\\"", {ADMIN}];
  query [label="Build retrieval query from\\nrule definition + pattern + shared categories"];
  qemb [label="Embed the query", {AI}];
  search [label="Cosine similarity search\\ntop 3 GG + top 2 DG + top 1 RS passages"];
  vs [label="Local vector store", {STORE}];
  key [label="OpenAI key set?", {DECISION}];
  local [label="Local narrative from evidence\\n(cites transaction IDs only)"];
  payload [label="Payload: case, linked order and item rows,\\nretrieved passages with citation IDs"];
  llm [label="gpt-4o-mini with guardrail instructions\\nexplain only · cite [GG-…]/[DG-…]/[RS-…] and [QB:order]\\ntreat purchase text as untrusted · store=False", {AI}];
  valid [label="Every citation is one of\\nthe retrieved passages?", {DECISION}];
  report [label="Review report + retrieved passages\\n(admin can check every citation)", {OUT}];
  notes [label="Admin records disposition and notes\\nDownload review (JSON)", {ADMIN}];

  start -> rules -> list -> open -> click -> query -> qemb -> search;
  vs -> search [style=dashed];
  search -> key;
  key -> local [label="no"];
  key -> payload [label="yes"];
  payload -> llm -> valid;
  valid -> report [label="yes"];
  valid -> local [label="no: discard\\nAI text"];
  local -> report;
  report -> notes;
}}"""

FLOW_UC2 = f"""digraph uc2 {{
{_STYLE}
  start [label="Admin opens the Reason & justification tab", {ADMIN}];
  scope [label="Approved, non-cancelled carts\\n(selected agency and financial years)"];
  rule [label="REASON rule on the reason text only\\nvague (e.g. QB2025) → Low\\noffline / email / refer / approval → Medium"];
  click [label="Admin clicks \\"Screen N unscreened carts\\"\\n(#welfare carts out of scope)", {ADMIN}];
  cache [label="Result cached for this cart,\\nmodel and prompt version?", {DECISION}];
  store [label="Screen cache\\n.cache/ai_screen", {STORE}];
  payload [label="Payload per cart: reason, item descriptions,\\ncategories, qty, prices (no price bands)\\nchunks of ≤ 25 items"];
  llm [label="gpt-4o-mini with justification prompt\\nfunction vs. stated purpose → BASE level per item\\nstrict JSON schema · temperature 0", {AI}];
  check [label="Validate: every item returned,\\nlevels in allowed list"];
  bands [label="Unit price after discount vs. OTHER carts' items\\nin the same Product_Category (all agencies)\\n→ price band per item"];
  more [label="More than 5\\ncomparison records?", {DECISION}];
  esc [label="90th percentile–max: +1 tier\\nabove max: +2 tiers, cap at Very High\\n(never lowers a tier; Uncertain not escalated)"];
  keep [label="Keep base level"];
  cart [label="Cart level = highest item level\\nDisplay: Very High→High · High/Medium→Medium · Low/Very Low→Low"];
  table [label="One row per cart: rule flag | AI-suggested tier\\nshown side by side, never merged\\nfilters · CSV download", {OUT}];
  detail [label="Cart detail: AI and price working, item table,\\nrelated guidance retrieved from the knowledge base\\nreviewer notes · JSON download", {OUT}];

  start -> scope;
  scope -> rule;
  scope -> click;
  scope -> bands;
  click -> cache;
  cache -> store [label="yes: reuse", style=dashed];
  cache -> payload [label="no"];
  payload -> llm -> check;
  check -> store [label="save"];
  store -> more;
  bands -> more;
  more -> esc [label="yes"];
  more -> keep [label="no"];
  esc -> cart; keep -> cart;
  rule -> table;
  cart -> table -> detail;
}}"""

FLOWCHARTS = {"overview": FLOW_OVERVIEW, "uc1": FLOW_UC1, "uc2": FLOW_UC2}
