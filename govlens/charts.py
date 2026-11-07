"""Altair charts, each answering one review question for the case or cart that is open.

* g2b_reset_chart: did one officer's spend run straight through the 1 Apr / 1 Oct reset,
  with the same goods, to a combined amount above the $6,000 limit?
* g2c_buyer_timeline: across the half-year, did different buyers in one cost centre buy the same category on
  the same days from the same seller (pointing to one need split across colleagues),
  or spread out over the half-year (pointing to independent needs)?
* dearest_comparisons (a table, not a chart): the most expensive items a price comparison
  rests on, so a reviewer can see whether the category mixes dissimilar goods.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from .casefacts import buyer_labels

# QB palette (quickbuy.gov.sg): blue for the mark that answers the question, orange as the second
# brand colour, greys for context. QB's own blue (#10069F) is too dark to see on a dark background,
# so the dark palette uses a lighter QB blue; the logo orange is darkened slightly on white.
QB_BLUE = "#10069F"
QB_ORANGE = "#D9661A"
PALETTES = {
    "light": {"highlight": QB_BLUE, "accent": QB_ORANGE, "grey": "#9aa5b1", "ink": "#334155",
              "muted": "#475569", "stroke": "white",
              "series": [QB_BLUE, QB_ORANGE, "#0F766E", "#8E2C8A", "#A16207"]},
    "dark": {"highlight": "#A5A0FF", "accent": "#F7984A", "grey": "#6B7280", "ink": "#D1D5DB",
             "muted": "#9CA3AF", "stroke": "#1F2937",
             "series": ["#A5A0FF", "#F7984A", "#2DD4BF", "#E879F9", "#FACC15"]},
}


def palette(theme_type: str | None = None) -> dict:
    """Chart colours for the app's light or dark theme (st.context.theme.type)."""
    return PALETTES["dark" if theme_type == "dark" else "light"]


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
                    officer_cap: float = 6000.0, colors: dict | None = None) -> alt.Chart:
    """Cumulative spend across the window, the reset date and the $6,000 limit.

    Orders are coloured by whether their product category was also bought on the other
    side of the reset, which is the question G2B leaves to the reviewer.
    """
    c = colors or palette()
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
    line = base.mark_line(interpolate="step-after", color=c["ink"], strokeWidth=2).encode(
        y=alt.Y("Cumulative:Q", title="Spend summed across the reset ($)")
    )
    points = base.mark_circle(opacity=0.95, stroke=c["stroke"], strokeWidth=1).encode(
        y="Cumulative:Q",
        size=alt.Size("Amount:Q", scale=alt.Scale(range=[90, 600]), legend=None),
        order=alt.Order("Layer:Q"),
        color=alt.Color("Match:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=400),
                        scale=alt.Scale(domain=["Category also bought on the other side", "Category on one side only"],
                                        range=[c["highlight"], c["grey"]])),
        tooltip=[
            alt.Tooltip("Date:T", format="%d %b %Y"), alt.Tooltip("Amount:Q", title="Order ($)", format=",.2f"),
            alt.Tooltip("Cumulative:Q", title="Summed so far ($)", format=",.2f"), "Category:N",
            "Seller:N", "Reason:N",
        ],
    )
    cap = alt.Chart(pd.DataFrame({"y": [officer_cap], "label": [f"${officer_cap:,.0f}: one period's limit"]}))
    cap_rule = cap.mark_rule(strokeDash=[6, 4], color=c["muted"]).encode(y="y:Q")
    cap_text = cap.mark_text(align="left", dx=4, dy=-7, color=c["muted"], fontSize=11).encode(
        y="y:Q", x=alt.value(0), text="label:N"
    )
    reset = alt.Chart(pd.DataFrame({"x": [boundary], "label": [f"Limit resets {boundary.day} {boundary:%b %Y}"]}))
    reset_rule = reset.mark_rule(color=c["grey"], strokeWidth=2).encode(x="x:T")
    reset_text = reset.mark_text(align="left", dx=5, y=8, color=c["muted"], fontSize=11).encode(x="x:T", text="label:N")
    return (line + points + cap_rule + cap_text + reset_rule + reset_text).properties(
        height=320, padding={"top": 14, "left": 5, "right": 5, "bottom": 5},
        title=alt.TitleParams(
            "Spend before and after the reset", anchor="start", fontSize=14, color=c["ink"], subtitleColor=c["muted"],
            subtitle=["QB applies the limit within each period, so a line above it is not a breach.",
                      "Blue: the same category was bought on both sides of the reset."],
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


def g2c_buyer_timeline(case: pd.Series, linked_items: pd.DataFrame, top_sellers: int = 5,
                       colors: dict | None = None) -> alt.Chart:
    """One row per buyer across the half-year: when each bought, how much, from which seller."""
    c = colors or palette()
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
    seller_colors = c["series"][: len(keep)] + [c["grey"]]
    bounds = _half_year_bounds(case.get("Period", ""))
    x_scale = alt.Scale(domain=[bounds[0], bounds[1]]) if bounds else alt.Undefined
    return alt.Chart(orders).mark_circle(opacity=0.8, stroke=c["stroke"], strokeWidth=1).encode(
        x=alt.X("Date:T", title=f"{case.get('Period', '')} (half financial year)", scale=x_scale,
                axis=alt.Axis(format="%b %Y", tickCount="month")),
        y=alt.Y("Buyer:N", title=None, sort=list(labels.values()), axis=alt.Axis(labelOverlap=False)),
        size=alt.Size("Amount:Q", scale=alt.Scale(range=[60, 700]), legend=None),
        color=alt.Color("Seller_Shown:N", title="Seller", scale=alt.Scale(domain=domain, range=seller_colors)),
        tooltip=[alt.Tooltip("Date:T", format="%d %b %Y"), "Buyer:N", alt.Tooltip("Amount:Q", title="Amount ($)", format=",.2f"),
                 "Orders:Q", "Seller:N", alt.Tooltip("Reason:N", title="First reason")],
    ).properties(
        height=max(160, 56 * len(labels)),
        title=alt.TitleParams(
            "Who bought, when, and from which seller", anchor="start", fontSize=14, color=c["ink"], subtitleColor=c["muted"],
            subtitle=["Dots lined up on the same dates, especially from one seller, can point to one need split "
                      "across colleagues;", "dots spread over the half-year point to separate needs."],
        ),
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
