"""Read-only views of one flagged case, used by the agent tools and the charts.

Everything here is plain pandas, so it is tested without CrewAI or an API key.
Buyers are shown as "Buyer A", "Buyer B"... (ordered by spend in the case) rather than
by their hashed e-mail; the same labels appear in the G2C chart. Outputs are capped so
an agent never receives an unbounded table.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .engine import case_items, case_orders

MAX_ROWS = 40
GROUP_KEYS = ("buyer", "seller", "date", "week", "month", "category", "side")


def buyer_labels(linked_items: pd.DataFrame) -> dict[str, str]:
    """Hashed buyer e-mail -> 'Buyer A' (highest spend in the case first)."""
    if linked_items.empty:
        return {}
    totals = (
        linked_items.groupby("Buyer_Corporate_Email")["Amount_After_Discount"].sum()
        .sort_values(ascending=False, kind="stable")
    )
    return {buyer: f"Buyer {_letters(i)}" for i, buyer in enumerate(totals.index)}


def _letters(i: int) -> str:
    out = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        out = chr(65 + rem) + out
    return out


def _money(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


class CaseFacts:
    """The orders and items behind one case, with the views an agent needs."""

    def __init__(self, case: pd.Series, orders: pd.DataFrame, detail: pd.DataFrame):
        self.case = case
        self.rule = str(case["Rule_ID"])
        self.items = case_items(case, detail)
        self.labels = buyer_labels(self.items)
        boundary = str(case.get("Boundary") or "")
        self.boundary = pd.Timestamp(boundary) if boundary and boundary != "nan" else None
        self.order_ids = [v.strip() for v in str(case["Evidence_Order_IDs"]).split("|") if v.strip()]
        self.frame = self._order_frame(case_orders(case, orders))

    def _order_frame(self, linked: pd.DataFrame) -> pd.DataFrame:
        cats = {
            str(order_id): sorted({str(c) for c in group["Product_Category"].dropna() if str(c)})
            for order_id, group in self.items.groupby("Order_ID")
        }
        item_amount = self.items.groupby("Order_ID")["Amount_After_Discount"].sum()
        rows = []
        for _, r in linked.iterrows():
            order_id = str(r["Order_ID"])
            date = pd.Timestamp(r["Event_Date"]).normalize()
            # G2B counts invoice totals; G2C counts item amounts (as the rules do).
            amount = r["Total_Amt_Payable"] if self.rule == "G2B" else item_amount.get(r["Order_ID"], 0.0)
            rows.append({
                "order_id": order_id,
                "date": date,
                "buyer": self.labels.get(r["Buyer_Corporate_Email"], "Buyer ?"),
                "seller": str(r.get("Seller_Name") or ""),
                "amount": _money(amount),
                "categories": cats.get(order_id, []),
                "reason": str(r.get("Reason_For_Purchase") or "")[:160],
                "side": (
                    ("before reset" if date < self.boundary else "after reset")
                    if self.boundary is not None else ""
                ),
            })
        frame = pd.DataFrame(rows)
        if frame.empty:
            frame = pd.DataFrame(columns=["order_id", "date", "buyer", "seller", "amount", "categories", "reason", "side"])
        return frame.sort_values(["date", "order_id"], kind="stable").reset_index(drop=True)

    @property
    def amount_basis(self) -> str:
        return ("invoice Total_Amt_Payable per order" if self.rule == "G2B"
                else "item Amount_After_Discount per order")

    # ---- views used by the agent tools -------------------------------------------------
    def overview(self) -> dict[str, Any]:
        f = self.frame
        by_buyer = f.groupby("buyer").agg(orders=("order_id", "size"), total=("amount", "sum"))
        out = {
            "case_id": str(self.case["Case_ID"]),
            "rule": self.rule,
            "pattern": str(self.case.get("Pattern", "")),
            "subject": str(self.case.get("Subject", "")) if self.rule == "G2C" else "one officer (Buyer A)",
            "review_priority": str(self.case["Risk_Tier"]),
            "score": str(self.case["Score"]),
            "score_breakdown": str(self.case["Score_Breakdown"]),
            "period": str(self.case.get("Period", "")),
            "reset_date": str(self.boundary.date()) if self.boundary is not None else None,
            "total_amount": _money(self.case["Total_Amount"]),
            "amount_above_6000": _money(self.case["Excess_Above_Threshold"]),
            "evidence_summary": str(self.case["Evidence_Summary"]),
            "orders": int(len(f)),
            "amount_basis": self.amount_basis,
            "first_order_date": str(f["date"].min().date()) if len(f) else None,
            "last_order_date": str(f["date"].max().date()) if len(f) else None,
            "distinct_sellers": int(f["seller"].nunique()),
            "buyers": [
                {"buyer": b, "orders": int(r.orders), "total": _money(r.total)}
                for b, r in by_buyer.sort_values("total", ascending=False).iterrows()
            ],
        }
        if self.boundary is not None:
            out["spend_by_side"] = {
                side: _money(total) for side, total in f.groupby("side")["amount"].sum().items()
            }
        return out

    def list_orders(self, buyer: str | None = None, seller: str | None = None, category: str | None = None,
                    side: str | None = None, date_from: str | None = None, date_to: str | None = None,
                    limit: int = MAX_ROWS) -> dict[str, Any]:
        f = self.frame
        if buyer:
            f = f[f["buyer"].str.lower() == buyer.strip().lower()]
        if seller:
            f = f[f["seller"].str.lower().str.contains(seller.strip().lower(), regex=False)]
        if category:
            f = f[f["categories"].map(lambda cs: any(category.strip().lower() in c.lower() for c in cs))]
        if side:
            f = f[f["side"].str.startswith(side.strip().lower().split()[0])]
        if date_from:
            f = f[f["date"] >= pd.Timestamp(date_from)]
        if date_to:
            f = f[f["date"] <= pd.Timestamp(date_to)]
        limit = max(1, min(int(limit or MAX_ROWS), MAX_ROWS))
        rows = [
            {**{k: v for k, v in r.items() if k != "date"}, "date": str(r["date"].date())}
            for r in f.head(limit).to_dict("records")
        ]
        return {"matching_orders": int(len(f)), "shown": len(rows), "amount_basis": self.amount_basis,
                "total_of_matching": _money(f["amount"].sum()), "orders": rows}

    def summarise(self, group_by: list[str]) -> dict[str, Any]:
        keys = [k.strip().lower() for k in group_by if k and k.strip()]
        bad = [k for k in keys if k not in GROUP_KEYS]
        if not keys or bad:
            return {"error": f"group_by must use only {list(GROUP_KEYS)}; got {group_by}"}
        if "side" in keys and self.boundary is None:
            return {"error": "'side' (before/after the reset) only applies to G2B cases"}
        f = self.frame.copy()
        f["week"] = f["date"].dt.to_period("W-SUN").astype(str)
        f["month"] = f["date"].dt.strftime("%Y-%m")
        if "category" in keys:
            f = f.explode("categories").rename(columns={"categories": "category"})
            f["category"] = f["category"].fillna("Unknown")
        f["date"] = f["date"].dt.strftime("%Y-%m-%d")
        grouped = (
            f.groupby(keys)
            .agg(orders=("order_id", "nunique"), total=("amount", "sum"), buyers=("buyer", "nunique"),
                 sellers=("seller", "nunique"), order_ids=("order_id", lambda s: sorted(set(s))[:10]))
            .reset_index()
            .sort_values(["total"], ascending=False, kind="stable")
        )
        groups = [
            {**{k: str(r[k]) for k in keys}, "orders": int(r["orders"]), "total": _money(r["total"]),
             "distinct_buyers": int(r["buyers"]), "distinct_sellers": int(r["sellers"]),
             "example_order_ids": list(r["order_ids"])}
            for _, r in grouped.head(MAX_ROWS).iterrows()
        ]
        note = "Amounts by category count each multi-category order's full amount in every category." if "category" in keys else ""
        return {"group_by": keys, "groups": len(grouped), "shown": len(groups), "amount_basis": self.amount_basis,
                "note": note, "rows": groups}
