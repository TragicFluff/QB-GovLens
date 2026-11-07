# QB GovLens Streamlit PoC

A QB-native governance review prototype for agency administrators. It runs on
masked QB Admin Portal exports and produces **review aids, not findings**.

- **Use case 1, split-purchase review (G2B and G2C tabs):** deterministic rules
  flag cases and each case opens with a chart of the pattern. On an admin's click,
  a three-agent **CrewAI** crew (evidence analyst, guidance researcher, report
  writer) queries the case with read-only tools, searches the built-in knowledge
  base and writes a report whose citations are checked in Python. The admin can
  then ask follow-up questions, answered by one agent with the same tools.
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
  `docs/flowcharts/` for slides), the agents, tools and skills, evaluation results, prompts,
  data coverage, the knowledge-base index, a retrieval check per rule, implementation details
  and limitations.

Login is a single hardcoded user (bootcamp minimum scope). The username and a salted
PBKDF2 hash of the password are in `govlens/auth.py`; the plaintext password is not in the
repository. To change the username and/or password, run `python scripts/make_password_hash.py`
from the app folder: it prompts for both and updates `govlens/auth.py` itself. Restart the app,
and push `govlens/auth.py` to GitHub to update a deployed app.

## Quick start

1. Python 3.10 to 3.13 virtual environment (CrewAI does not support 3.14 yet), then
   `pip install -r requirements.txt`. This installs CrewAI and moves `openai` to 2.x,
   which CrewAI requires.
2. Put your key in `.env` (already git-ignored) as `OPENAI_API_KEY=sk-...`,
   or set it as an environment variable. On Streamlit Community Cloud, add it
   under the app's Secrets as `OPENAI_API_KEY = "sk-..."`.
3. `streamlit run app.py` and sign in. The built-in dataset is the masked sample in
   `demo_data/` (Invoices, Carts, InvoiceItems).
4. Run tests with `python -m pytest -q tests/` (no API calls are made).

Without a key the app still runs: retrieval falls back to keyword matching
(labelled in the UI) and the AI features are switched off. Without CrewAI (for
example on Python 3.14), case reviews use a single AI call instead of the crew.

## Look and feel

`.streamlit/config.toml` sets a dark theme in QuickBuy@SGov's colours (deep QB-blue sidebar,
orange controls, light QB-blue links, Inter typeface). Charts switch to a matching dark palette
(`govlens/charts.py`), so QB blue and orange stay readable on the dark page.

## Agent crew and skills

`govlens/crew.py` builds the review crew and the follow-up Q&A agent. Their tools
(`govlens/casefacts.py`) are read-only views of the open case: `case_overview`,
`list_orders`, `summarise_orders` and `search_guidance`. Buyers appear as Buyer A,
Buyer B... The rules, tiers and scores are never visible to the agents as things they
can change.

Every model's instructions are **skills**: `skills/<name>/SKILL.md` files in the
Agent Skills format (front matter with name and description, then Markdown):

| Skill | Attached to |
|---|---|
| `govlens-evidence-analysis` | Evidence analyst |
| `govlens-guidance-research` | Guidance researcher |
| `govlens-case-report` | Report writer |
| `govlens-case-qa` | Follow-up Q&A agent |
| `govlens-citations` | Whole crew |
| `govlens-purchase-justification` | Purchase-justification screen (read directly as the system prompt) |

Citations are checked in Python twice: as a CrewAI task guardrail (the writer is
told what failed and retries, at most twice) and again after the crew. If the crew
fails, the app falls back to the single-call explanation, then to a local one.
CrewAI telemetry and tracing are switched off in code, and the task outputs CrewAI
keeps on disk are cleared after each run.

## Evaluation

- `python scripts/evaluate_reviews.py` (needs the API key; a few US cents): runs the
  crew and the single-call explanation on every G2B/G2C case and saves
  `evaluation/review_runs.csv` (citation check, seconds, tokens, dollar figures not
  traceable to the model's input), `evaluation/review_reports.md` (both reports per case
  as Report A/B in random order) and a blank `evaluation/review_labels.csv` for blind rating.
- `python scripts/evaluate_justification.py` (no key): the first run writes
  `evaluation/justification_labels.csv` with 12 carts sampled across tiers; fill in
  `your_tier` without looking at the app, run it again to see agreement.

Commit the `evaluation/` files and the Methodology page shows the results.

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
   categories, quantities, unit and total prices; **no price positions**) and the
   passages, and returns strict JSON: per-item core function, tier (**High**: clear
   red flags that warrant investigation; **Medium**: plausible but with justification
   gaps; **Low**: broadly appropriate; or Uncertain) and rationale, an assessment that
   cites the passages, a summary and the citation IDs. These are the same three tiers
   the app shows. It must not invent a purpose the reason does not state: label-only
   reasons are a documentation gap (Medium for everyday items, High for specialised or
   costly items). Citations outside the supplied passages are rejected. Carts with
   more than 25 items are sent in chunks.
3. Python computes unit price after discount (`Amount_After_Discount / Qty`) and
   compares it with other carts' items in the same `Product_Category` across all
   agencies. With more than 5 comparison records, an item that costs more than all
   of them moves up **one** tier (capped at High). Items in the top 10% are noted in
   the Why column but keep their tier, because categories are broad. Price never
   lowers a tier.
4. The cart takes its highest item tier, raised to Medium if the reason has approval
   wording. Carts without an AI result show a provisional rule-only tier.
5. AI results for the masked sample are **precomputed and shipped** in
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
5. Under **Advanced settings**, choose Python 3.12 (CrewAI needs 3.13 or lower). An app
   already deployed on 3.14 keeps working, but without the crew; its Python version can only
   be changed by deleting the app and redeploying it with the same subdomain and secrets.

## Not implemented (PoC limits)

User roles and agency access control (one hardcoded login only), immutable audit
trail, production data integration and security review.
