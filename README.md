# QB GovLens Streamlit PoC

A QB-native governance review prototype for agency administrators. It runs on
masked QB Admin Portal exports and produces **review aids, not findings**.

- **Use case 1, split-purchase review (G2B and G2C tabs):** deterministic rules
  flag cases; on an admin's click, passages are retrieved from the built-in
  knowledge base by embedding similarity and an OpenAI model writes an
  explanation whose citations are verified against the retrieved passages.
- **Use case 2, reason & justification (one tab):** per cart, a deterministic
  REASON flag (vague or approval wording) and an AI-suggested tier (an LLM rates
  the items against the stated reason; Python applies category price-band
  escalation), shown side by side and never merged.

## Pages and sign-in

`app.py` shows a sign-in form, then three pages:

- **Governance review** (main page): the required educational-use disclaimer and three tabs:
  G2B (spend across the 6-month reset), G2C (same cost centre and category) and
  Reason & justification.
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
- **REASON:** follows Governance Guide p.20. Vague reasons (e.g. `QB2025`,
  `QB buy`, fewer than two meaningful words and no purpose hashtag) = Low;
  keywords offline / email / refer / approval = Medium. Deliberately broad.

## AI justification screen

1. The LLM receives one cart (reason, item descriptions, categories, quantities,
   unit and total prices; **no price bands**) and returns strict JSON: per-item
   core function, base risk level (Very Low ... Very High, or Uncertain) and
   rationale, plus an assessment and summary. Carts with more than 25 items are
   sent in chunks.
2. Python computes unit price after discount (`Amount_After_Discount / Qty`) and
   compares it with other carts' items in the same `Product_Category` across all
   agencies. With more than 5 comparison records: 90th percentile to maximum = +1
   tier, above maximum = +2, capped at Very High. Price never lowers a tier.
3. The cart takes its highest item tier. Display: Very High = High; High and
   Medium = Medium; Low and Very Low = Low; Uncertain stays Uncertain.
4. Results are cached per cart, model and prompt version in `.cache/ai_screen/`,
   so screening runs once per dataset. Download the list as CSV from the tab.

The chat model (`gpt-4o-mini`) and embedding model are fixed in `govlens/ui.py`.
Changing the chat model invalidates the cached AI screen results.

## Deploying to Streamlit Community Cloud

1. Push this folder to a **private** GitHub repository (`.env` and `.cache/` are git-ignored).
2. In Streamlit Community Cloud, create an app from the repo with main file `app.py`.
3. Under the app's **Secrets**, add `OPENAI_API_KEY = "sk-..."`.
4. Open the app, sign in, and run the AI screen once (Reason & justification tab) so results are cached.
   (The cache resets if the app restarts; re-running only re-sends uncached carts.)

## Not implemented (PoC limits)

User roles and agency access control (one hardcoded login only), immutable audit
trail, production data integration and security review.
