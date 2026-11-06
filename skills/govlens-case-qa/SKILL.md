---
name: govlens-case-qa
description: Answer an administrator's follow-up question about one open G2B or G2C case by querying the case data and the knowledge base with the tools.
metadata:
  version: "1.0"
  used-by: case Q&A agent
---

# Answering questions about the open case

The administrator has one case open and asks a question about it, for example "did any buyer order from the same seller on the same day?" or "what does the guide say about seller quantity limits?".

## Method

1. Decide what the question needs: case facts, guidance, or both.
2. For facts, use the tools; do not estimate. `summarise_orders` answers most "how many / how much / who / when" questions; `list_orders` gives the rows and reasons behind them.
3. For guidance, call `search_guidance` with a search aimed at the question.
4. If the question is outside this case or outside the data (for example who a buyer is, or whether someone acted improperly), say what the data can and cannot show, and suggest what the administrator could check instead.

## Answer

Answer first, in one or two sentences, then the supporting facts with `[QB:order_id]` and guidance citations. Keep it under about 200 words. Same limits as the report: no verdicts on intent, no breach or fraud language, no re-scoring.
