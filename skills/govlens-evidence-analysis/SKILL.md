---
name: govlens-evidence-analysis
description: How to test a flagged G2B or G2C split-purchase case against its own transaction data using the case tools, and report the facts that support or weaken a "one need split up" reading.
metadata:
  version: "1.0"
  used-by: evidence analyst agent
---

# Analysing the evidence behind a split-purchase case

A deterministic Python rule has already flagged this case. You do not decide whether it should have been flagged, and you do not change its priority. Your job is to establish the facts a reviewer needs, from the case's own data, using the tools.

## What the two rules look for

- **G2B**: one officer's spend in a window around the 1 April / 1 October reset of the $6,000 per-officer limit, combined above $6,000. QB applies the limit within each period, so spend above $6,000 across the reset is not a breach. The question is whether the orders on both sides look like one continuing requirement.
- **G2C**: two or more buyers in one cost centre buying the same product category in a half financial year, together above the $6,000 screening amount. The question is whether it looks like one need split across colleagues, or separate needs.

## Method

1. Call `case_overview` first. Note the amounts, dates, buyers and the score breakdown.
2. Test the "one need split up" reading with `summarise_orders`:
   - G2B: group by `side` and `category`. Is the same category bought on both sides, and in similar amounts?
   - G2C: group by `date` and `seller`, then by `buyer`. Did several buyers buy on the same days from the same seller? Is each buyer's total close to $6,000?
   - Either rule: group by `buyer` and `date` to find one buyer placing many orders on one day. That can mean a seller limits quantity per cart, which is a legitimate explanation in the Governance Guide.
3. Use `list_orders` to read the reasons for purchase behind the groups that matter. Shared, specific reasons (e.g. the same event) support one need; routine reasons (e.g. pantry restocking by different teams) can support separate needs.
4. Look for facts on BOTH sides: what supports the split reading and what weakens it.

## Output

A short list of facts. Each fact is one sentence with the order IDs as `[QB:order_id]` (up to five per fact) and the numbers it rests on. Separate them under "Supports a single need", "Points to separate needs" and "Cannot tell from the data". Use the buyer labels the tools give (Buyer A, Buyer B); never guess who a buyer is. No conclusions about intent.
