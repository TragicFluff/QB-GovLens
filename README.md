# QB GovLens Streamlit PoC

A QB-native governance review prototype for agency administrators. It runs on
masked QB Admin Portal exports and produces **review aids, not findings**.

- **Use case 1, split-purchase review (G2B and G2C tabs):** deterministic rules
  flag cases; on an admin's click, passages are retrieved from the built-in
  knowledge base by embedding similarity and an OpenAI model writes an
  explanation whose citations are verified against the retrieved passages.
- **Use case 2, purchase justification (one tab):** one tier per cart combining a
  deterministic check of the reason text (vague or approval wording), an LLM
  assessment of the items against the stated reason that cites retrieved
  guidance, and category price-band escalation, with a "Why" column.

## Pages and sign-in

`app.py` shows a sign-in form, then three pages:

- **Governance review** (main page): the required educational-use disclaimer and three tabs:
  G2B (spend across the 6-month reset), G2C (same cost centre and category) and
  Purchase justification.
- **About Us**: scope, objectives, data sources, features and guardrails.
- **Methodology**: data flows, a flowchart for each use case (also exported as PNG/SVG in
  `docs/flowcharts/` for slides), prompts, data coverage, the knowledge-base index, a
  retrieval check per rule, implementation details and limitations.

Login is a single hardcoded user (bootcamp minimum scope). The username and a salted
PBKDF2 hash of the password are in `govlens/auth.py`; the plaintext password is not in the
repository. To change the username and/or password, run `python scripts/make_password_hash.py`
from the app folder: it prompts for both and updates `govlens/auth.py` itself. Restart the app,
and push `govlens/auth.py` to GitHub to update a deployed app.

## Quick start

1. Python 3.11+ virtual environment, then `pip install -r requirements.txt`.
2. Put your key in `.env` (already git-ignored) as `OPENAI_API_KEY=sk-...`,
   or set it as an environment variable. On Streamlit Community Cloud, add it
   under the app's Secrets as `OPENAI_API_KEY = "sk-..."`.
3. `streamlit run app.py` and sign in. The built-in dataset is the masked sample in
   `demo_data/` (Invoices, Carts, InvoiceItems).
4. Run tests with `python -m pytest -q tests/` (no API calls are made).

Without a key the app still runs: retrieval falls back to keyword matching
(labelled in the UI) and the AI features are switched off.

## Knowledge base (`knowledge_base/`)

| File | Source | Citations |
|---|---|---|
| `governance_guide.md` | Official QB Admin Portal Governance Guide, curated: one passage per suggested check and data topic, page numbers kept | `GG-CHECK-SPLIT`, `GG-CHECK-REASONS`, ... |
| `data_glossary.md` | Official Data Glossary, field descriptions verbatim for the fields GovLens reads, grouped by topic | `DG-ITEM-PRICE-QTY`, ... |
| `govlens_rule_spec.md` | GovLens's own rule documentation, **labelled as not policy** | `RS-G2B`, `RS-AI-SCREEN`, ... |

The rule spec exists because the official guide does not state the
1 April / 1 October reset dates that G2B relies on; it lets explanations
distinguish "the guide says" from "this tool's rule does".

Regenerate the glossary file after a glossary update with
`python scripts/build_glossary_kb.py "demo_data/Data Glossary of QB Admin Portal Data (Headers).xlsx"`.
Edit the other two files directly; each `## [ID] Title` section is one passage.

## Retrieval

Passages are embedded with OpenAI `text-embedding-3-small` (fixed in `govlens/ui.py`) into a
local NumPy vector store saved at `.cache/kb_vectors_<model>_<fingerprint>.npz`.
The corpus is re-embedded only when the knowledge base or model changes. Each
query is embedded and matched by cosine similarity, taking the top 3 Governance
Guide, top 2 Data Glossary and top 1 rule-spec passages. The **Methodology** page
shows which passages each rule retrieves, with scores.

## Rules (v1.1)

- **Event date:** `Order_Date` (Invoices file) for every time-window rule.
- **Scope:** approved (`Cart_Status`), non-cancelled carts only; welfare
  (`#welfare`) purchases excluded from G2B, G2C and the AI screen.
- **G2B:** same agency/officer, spend in both windows (30 days by default) around
  1 Apr / 1 Oct, combined > $6,000 (the system-enforced officer limit, fixed in
  code); shared category and reason words raise priority.
- **G2C:** same agency / cost centre / product category / half-FY, at least two
  material buyers (>10% share) with combined > $6,000 screening amount.
- **REASON (reason check):** follows Governance Guide p.20. Flags vague reasons
  (e.g. `QB2025`, `QB buy`, fewer than two meaningful words and no purpose
  hashtag) and approval wording (offline / email / refer / approval). Deliberately
  broad. Feeds the purchase-justification tier below.

## Purchase justification (one tier per cart)

1. For each cart, a query built from the reason and product categories retrieves
   the top 3 Governance Guide and top 1 rule-spec passages (embeddings).
2. The LLM receives the cart (reason, the REASON pre-checks, item descriptions,
   categories, quantities, unit and total prices; **no price bands**) and the
   passages, and returns strict JSON: per-item core function, base risk level
   (Very Low ... Very High, or Uncertain) and rationale, an assessment that cites
   the passages, a summary and the citation IDs. It must not invent a purpose the
   reason does not state: label-only reasons are a documentation gap (Medium for
   everyday items, High for specialised or costly items). Citations outside the
   supplied passages are rejected. Carts with more than 25 items are sent in chunks.
2. Python computes unit price after discount (`Amount_After_Discount / Qty`) and
   compares it with other carts' items in the same `Product_Category` across all
   agencies. With more than 5 comparison records: 90th percentile to maximum = +1
   tier, above maximum = +2, capped at Very High. Price never lowers a tier.
3. The cart takes its highest item level after price escalation, raised to Medium
   if the reason has approval wording. Display: Very High = High; High and Medium
   = Medium; Low and Very Low = Low; Uncertain stays Uncertain. Carts without an AI
   result show a provisional rule-only tier.
4. AI results for the masked sample are **precomputed and shipped** in
   `precomputed/ai_screen_results.json`, keyed by cart data, model and prompt
   version. Generate them locally with `python scripts/precompute_ai_screen.py`
   (needs `OPENAI_API_KEY` in `.env`), then commit and push the file. Re-run it
   whenever the prompt version, the chat model or the sample data changes; it only
   re-sends carts without a current result.

The chat model (`gpt-4o-mini`) and embedding model are fixed in `govlens/models.py`.

## Deploying to Streamlit Community Cloud

1. Push this folder to a **private** GitHub repository (`.env` and `.cache/` are git-ignored).
2. In Streamlit Community Cloud, create an app from the repo with main file `app.py`.
3. Under the app's **Secrets**, add `OPENAI_API_KEY = "sk-..."`.
4. Commit `precomputed/ai_screen_results.json` (see above) so the deployed app shows AI
   results without anyone running the assessment or spending API credit.

## Not implemented (PoC limits)

User roles and agency access control (one hardcoded login only), immutable audit
trail, production data integration and security review.
