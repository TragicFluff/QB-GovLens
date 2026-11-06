"""Blind check of the purchase-justification tier against a human reviewer.

Usage (from the project folder; no API key needed):
    python scripts/evaluate_justification.py

First run: writes evaluation/justification_labels.csv with 12 carts sampled across tiers
and reason types. GovLens's tier is NOT in the columns you fill in: read each cart's reason
and items, then type High, Medium or Low in your_tier (and a note if useful).

Later runs: prints how often your tier matches GovLens's and where they differ.
The Methodology page shows the same result once the file is filled in.
"""

from __future__ import annotations

from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import pandas as pd  # noqa: E402

from govlens import evaluation as ev  # noqa: E402
from govlens import justification as js  # noqa: E402
from govlens.demo import load_masked_sample  # noqa: E402
from govlens.engine import analyse  # noqa: E402
from govlens.models import CHAT_MODEL  # noqa: E402


def tier_table() -> tuple[pd.DataFrame, pd.DataFrame]:
    _, orders, detail, _ = analyse(*load_masked_sample())
    items = js.add_price_bands(js.build_items(orders, detail))
    eligible = js.eligible_carts(items)
    results = js.cached_results(items, eligible["Cart_ID"].tolist(), CHAT_MODEL, js.ScreenCache())
    rows = [js.combined_tier(items, c, str(r), results.get(c))
            for c, r in zip(eligible["Cart_ID"], eligible["Reason_For_Purchase"])]
    table = pd.DataFrame(rows).merge(eligible[["Cart_ID", "Event_Date", "Cart_Item_Total"]], on="Cart_ID")
    return table[table["AI_Level"].fillna("").astype(str) != ""], items  # carts with an AI result


def describe_items(items: pd.DataFrame, cart_id: str, limit: int = 6) -> str:
    rows = items[items["Cart_ID_Effective"] == cart_id]
    parts = [f"{int(r.Qty_Num)} x {str(r.Item_Desc)[:70]} (${r.Unit_Price_After_Discount:,.2f}, {r.Product_Category})"
             for r in rows.head(limit).itertuples()]
    more = len(rows) - limit
    return " | ".join(parts) + (f" | ... and {more} more item(s)" if more > 0 else "")


def main() -> int:
    table, items = tier_table()
    labels = ev.read_csv(ev.JUSTIFICATION_LABELS)
    if labels is None:
        sample = ev.stratified_carts(table)
        form = pd.DataFrame({
            "cart_id": sample["Cart_ID"],
            "date": pd.to_datetime(sample["Event_Date"]).dt.date.astype(str),
            "reason_for_purchase": sample["Reason_For_Purchase"],
            "cart_total": sample["Cart_Item_Total"].round(2),
            "items": [describe_items(items, c) for c in sample["Cart_ID"]],
            "your_tier": "", "your_note": "",
        })
        ev.EVAL_DIR.mkdir(exist_ok=True)
        form.to_csv(ev.JUSTIFICATION_LABELS, index=False, encoding="utf-8-sig")  # opens cleanly in Excel
        print(f"Wrote {ev.JUSTIFICATION_LABELS.relative_to(APP_DIR)}: fill in your_tier (High/Medium/Low), "
              "then run this script again.")
        return 0
    labels = labels.merge(table[["Cart_ID", "Tier", "Level", "Why"]].rename(
        columns={"Cart_ID": "cart_id", "Tier": "govlens_tier", "Level": "govlens_level", "Why": "govlens_why"}),
        on="cart_id", how="left")
    result = ev.agreement(labels)
    if not result["labelled"]:
        print("No labels yet: fill in your_tier (High/Medium/Low) in", ev.JUSTIFICATION_LABELS)
        return 0
    print(f"Labelled carts: {result['labelled']}; exact agreement {result['exact_agreement']:.0%}; "
          f"GovLens higher than you: {result['govlens_higher']}; lower: {result['govlens_lower']}")
    print("Rows = your tier, columns = GovLens tier:")
    print(pd.DataFrame(result["confusion"]).T)
    diff = labels[(labels["your_tier"].isin(ev.TIERS)) & (labels["your_tier"] != labels["govlens_tier"])]
    for r in diff.itertuples():
        print(f"- {r.cart_id[:8]}: you {r.your_tier}, GovLens {r.govlens_tier} ({r.govlens_why})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
