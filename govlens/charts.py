"""Altair charts, each answering one review question for the case or cart that is open.

* g2b_reset_chart: did one officer's spend run straight through the 1 Apr / 1 Oct reset,
  with the same goods, to a combined amount above the $6,000 limit?
* g2c_buyer_timeline: across the half-year, did different buyers in one cost centre buy the same category on
  the same days from the same seller (pointing to one need split across colleagues),
  or spread out over the half-year (pointing to independent needs)?
* price_position_chart: is an item's price escalation a genuine outlier, or does the
  product category mix dissimilar goods? Hover over the grey marks to see what the
  item is being compared with.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from .casefacts import buyer_labels

GREY = "#9aa5b1"
ACCENT = "#c2410c"
INK = "#334155"


def _first_category(detail: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    for order_id, group in detail.groupby("Order_ID"):
        cats = sorted({str(c) for c in group["Product_Category"].dropna() if str(c)})
        out[order_id] = cats[0] if len(cats) == 1 else ("Multiple categories" if cats else "Unknown")
    return out


def _categories(detail: pd.DataFrame) -> dict[str, set[str]]:
    return {
        order_id: {str(c) for c in group["Product_Category"].dropna() if str(c)}
        for order_id, group in detail.groupby("Order_ID")
    }


def g2b_reset_chart(case: pd.Series, linked_orders: pd.DataFrame, linked_items: pd.DataFrame,
                    officer_cap: float = 6000.0) -> alt.Chart:
    """Cumulative spend across the window, the reset date and the $6,000 limit.

    Orders are coloured by whether their product category was also bought on the other
    side of the reset, which is the question G2B leaves to the reviewer.
    """
    data = linked_orders[["Order_ID", "Event_Date", "Total_Amt_Payable", "Seller_Name", "Reason_For_Purchase"]]
    data = data.sort_values("Event_Date").copy()
    boundary = pd.Timestamp(case["Boundary"])
    data["Date"] = pd.to_datetime(data["Event_Date"])
    # Plain Python here: pandas 3 can turn mapped sets into Arrow lists.
    cats = _categories(linked_items)
    order_ids, dates = data["Order_ID"].astype(str).tolist(), data["Date"].tolist()
    before = set().union(set(), *(cats.get(o, set()) for o, d in zip(order_ids, dates) if d < boundary))
    after = set().union(set(), *(cats.get(o, set()) for o, d in zip(order_ids, dates) if d >= boundary))
    both = before & after
    first = _first_category(linked_items)
    data["Category"] = [first.get(o, "Unknown") for o in order_ids]
    data["Match"] = [
        "Category also bought on the other side" if cats.get(o, set()) & both else "Category on one side only"
        for o in order_ids
    ]
    data["Cumulative"] = data["Total_Amt_Payable"].astype(float).cumsum().round(2)
    data["Amount"] = data["Total_Amt_Payable"].astype(float)
    data["Seller"] = data["Seller_Name"].fillna("").astype(str)
    data["Reason"] = data["Reason_For_Purchase"].fillna("").astype(str).str.slice(0, 80)
    data["Layer"] = (data["Match"] != "Category on one side only").astype(int)  # matches drawn on top
    data = data[["Date", "Amount", "Cumulative", "Category", "Match", "Seller", "Reason", "Layer"]]

    base = alt.Chart(data).encode(x=alt.X("Date:T", title=None, axis=alt.Axis(format="%d %b")))
    line = base.mark_line(interpolate="step-after", color=INK, strokeWidth=2).encode(
        y=alt.Y("Cumulative:Q", title="Spend summed across the reset ($)")
    )
    points = base.mark_circle(opacity=0.95, stroke="white", strokeWidth=1).encode(
        y="Cumulative:Q",
        size=alt.Size("Amount:Q", scale=alt.Scale(range=[90, 600]), legend=None),
        order=alt.Order("Layer:Q"),
        color=alt.Color("Match:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=400),
                        scale=alt.Scale(domain=["Category also bought on the other side", "Category on one side only"],
                                        range=[ACCENT, GREY])),
        tooltip=[
            alt.Tooltip("Date:T", format="%d %b %Y"), alt.Tooltip("Amount:Q", title="Order ($)", format=",.2f"),
            alt.Tooltip("Cumulative:Q", title="Summed so far ($)", format=",.2f"), "Category:N",
            "Seller:N", "Reason:N",
        ],
    )
    cap = alt.Chart(pd.DataFrame({"y": [officer_cap], "label": [f"${officer_cap:,.0f}: one period's limit"]}))
    cap_rule = cap.mark_rule(strokeDash=[6, 4], color="#64748b").encode(y="y:Q")
    cap_text = cap.mark_text(align="left", dx=4, dy=-7, color="#475569", fontSize=11).encode(
        y="y:Q", x=alt.value(0), text="label:N"
    )
    reset = alt.Chart(pd.DataFrame({"x": [boundary], "label": [f"Limit resets {boundary.day} {boundary:%b %Y}"]}))
    reset_rule = reset.mark_rule(color=GREY, strokeWidth=2).encode(x="x:T")
    reset_text = reset.mark_text(align="left", dx=5, y=8, color="#475569", fontSize=11).encode(x="x:T", text="label:N")
    return (line + points + cap_rule + cap_text + reset_rule + reset_text).properties(
        height=320, padding={"top": 14, "left": 5, "right": 5, "bottom": 5},
        title=alt.TitleParams(
            "Spend before and after the reset", anchor="start", fontSize=14,
            subtitle="QB applies the limit within each period, so a line above it is not a breach. "
                     "Orange: the same category was bought on both sides.",
        ),
    )


def _half_year_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """'FY2025-H2' -> (1 Oct 2025, 31 Mar 2026)."""
    try:
        fy, half = str(period).split("-")
        year = int(fy[2:])
    except ValueError:
        return None
    if half == "H1":
        return pd.Timestamp(year, 4, 1), pd.Timestamp(year, 9, 30)
    return pd.Timestamp(year, 10, 1), pd.Timestamp(year + 1, 3, 31)


def g2c_buyer_timeline(case: pd.Series, linked_items: pd.DataFrame, top_sellers: int = 5) -> alt.Chart:
    """One row per buyer across the half-year: when each bought, how much, from which seller."""
    orders = (
        linked_items.groupby(["Order_ID", "Buyer_Corporate_Email"], as_index=False)
        .agg(Date=("Event_Date", "min"), Amount=("Amount_After_Discount", "sum"),
             Seller=("Seller_Name", "first"), Reason=("Reason_For_Purchase", "first"))
    )
    orders["Date"] = pd.to_datetime(orders["Date"]).dt.normalize()
    totals = orders.groupby("Buyer_Corporate_Email")["Amount"].sum()
    labels = {b: f"{name} (${totals[b]:,.0f})" for b, name in buyer_labels(linked_items).items()}
    orders["Buyer"] = orders["Buyer_Corporate_Email"].map(labels)
    orders["Date"] = pd.to_datetime(orders["Date"])
    orders["Amount"] = orders["Amount"].astype(float)
    # Colour the sellers used by the most buyers; the rest are grey.
    reach = orders.groupby("Seller")["Buyer"].nunique().sort_values(ascending=False)
    keep = [s for s in reach.index[:top_sellers]]
    orders["Seller"] = orders["Seller"].fillna("").astype(str)
    orders["Seller_Shown"] = orders["Seller"].where(orders["Seller"].isin(keep), "Other sellers")
    orders["Reason"] = orders["Reason"].fillna("").astype(str).str.slice(0, 80)
    # One dot per buyer, day and seller; the tooltip gives the number of orders behind it.
    orders = (
        orders.groupby(["Buyer", "Date", "Seller", "Seller_Shown"], as_index=False)
        .agg(Amount=("Amount", "sum"), Orders=("Reason", "size"), Reason=("Reason", "first"))
    )
    domain = keep + (["Other sellers"] if (orders["Seller_Shown"] == "Other sellers").any() else [])
    palette = ["#c2410c", "#1d4ed8", "#0f766e", "#a16207", "#7c3aed"][: len(keep)] + [GREY]
    bounds = _half_year_bounds(case.get("Period", ""))
    x_scale = alt.Scale(domain=[bounds[0], bounds[1]]) if bounds else alt.Undefined
    return alt.Chart(orders).mark_circle(opacity=0.8, stroke="white", strokeWidth=1).encode(
        x=alt.X("Date:T", title=f"{case.get('Period', '')} (half financial year)", scale=x_scale,
                axis=alt.Axis(format="%b %Y", tickCount="month")),
        y=alt.Y("Buyer:N", title=None, sort=list(labels.values()), axis=alt.Axis(labelOverlap=False)),
        size=alt.Size("Amount:Q", scale=alt.Scale(range=[60, 700]), legend=None),
        color=alt.Color("Seller_Shown:N", title="Seller", scale=alt.Scale(domain=domain, range=palette)),
        tooltip=[alt.Tooltip("Date:T", format="%d %b %Y"), "Buyer:N", alt.Tooltip("Amount:Q", title="Amount ($)", format=",.2f"),
                 "Orders:Q", "Seller:N", alt.Tooltip("Reason:N", title="First reason")],
    ).properties(
        height=max(160, 56 * len(labels)),
        title=alt.TitleParams(
            "Who bought, when, and from which seller", anchor="start", fontSize=14,
            subtitle="Dots lined up on the same dates, especially from one seller, can point to one need split "
                     "across colleagues; dots spread over the half-year point to separate needs.",
        ),
    )


def price_position_chart(cart_items: pd.DataFrame, all_items: pd.DataFrame) -> alt.Chart | None:
    """Each item's unit price against other carts' items in its category (log scale)."""
    rows, marks, refs = [], [], []
    for _, item in cart_items.iterrows():
        if not item.get("More_Than_5_Records", False):
            continue
        label = f"{item['Item_Ref']} · {item['Product_Category']}"
        peers = all_items[
            (all_items["Product_Category"] == item["Product_Category"])
            & (all_items["Cart_ID_Effective"] != item["Cart_ID_Effective"])
        ]
        for _, peer in peers.iterrows():
            rows.append({"Row": label, "Price": float(peer["Unit_Price_After_Discount"]),
                         "Item": str(peer.get("Item_Desc") or "")[:70]})
        marks.append({"Row": label, "Price": float(item["Unit_Price_After_Discount"]),
                      "Item": str(item.get("Item_Desc") or "")[:70], "Band": item["Price_Band"]})
        refs += [{"Row": label, "Price": float(item["Peer_P90"]), "Ref": "90th percentile"},
                 {"Row": label, "Price": float(item["Peer_Max"]), "Ref": "Maximum"}]
    if not marks:
        return None
    peers_df, marks_df, refs_df = pd.DataFrame(rows), pd.DataFrame(marks), pd.DataFrame(refs)
    order = list(dict.fromkeys(marks_df["Row"]))
    x = alt.X("Price:Q", title="Unit price after discount ($, log scale)", scale=alt.Scale(type="log"))
    y = alt.Y("Row:N", title=None, sort=order)
    peer_layer = alt.Chart(peers_df).mark_tick(color=GREY, opacity=0.55, thickness=1.5, size=18).encode(
        x=x, y=y, tooltip=[alt.Tooltip("Price:Q", format=",.2f"), alt.Tooltip("Item:N", title="Compared with")]
    )
    ref_layer = alt.Chart(refs_df).mark_tick(thickness=2.5, size=26).encode(
        x="Price:Q", y=y,
        color=alt.Color("Ref:N", title="Category reference",
                        scale=alt.Scale(domain=["90th percentile", "Maximum"], range=["#64748b", INK])),
        tooltip=["Ref:N", alt.Tooltip("Price:Q", format=",.2f")],
    )
    item_layer = alt.Chart(marks_df).mark_point(shape="diamond", filled=True, size=190, color=ACCENT).encode(
        x="Price:Q", y=y, tooltip=[alt.Tooltip("Price:Q", title="This item ($)", format=",.2f"), "Item:N", "Band:N"]
    )
    return (peer_layer + ref_layer + item_layer).properties(
        height=max(90, 60 * len(order)),
        title=alt.TitleParams("This cart's items (orange) against other purchases in the same category",
                              anchor="start", fontSize=14),
    )


def dearest_comparisons(item: pd.Series, all_items: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """The n dearest items from other carts in the same category: what the price band compares with."""
    peers = all_items[
        (all_items["Product_Category"] == item["Product_Category"])
        & (all_items["Cart_ID_Effective"] != item["Cart_ID_Effective"])
    ]
    top = peers.sort_values("Unit_Price_After_Discount", ascending=False).head(n)
    return pd.DataFrame({
        "Compared with": top["Item_Desc"].fillna("").astype(str).str.slice(0, 90),
        "Unit price ($)": top["Unit_Price_After_Discount"].astype(float).round(2),
        "Order date": pd.to_datetime(top["Event_Date"]).dt.strftime("%d %b %Y"),
    }).reset_index(drop=True)
