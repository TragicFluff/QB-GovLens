"""Auditable, deterministic G2B/G2C governance signals and reason checks.

IMPORTANT: These rules identify patterns for human review. They do not determine
breaches, intent, fraud, or whether an Invitation to Quote was required.

Input is the QB Admin Portal Invoices, InvoiceItems and Carts exports. Order_Date
(Invoices file) is the event date for every time-window rule. Only approved,
non-cancelled carts are screened, per the Governance Guide's instruction to
filter approved carts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import math
import re
from typing import Any

import pandas as pd

RULE_VERSION = "govlens-poc-v1.1"

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "our", "the", "their", "this",
    "to", "was", "were", "with", "purchase", "purchases", "buy",
    "buying", "items", "item", "order", "orders", "office", "general",
    "required", "need", "needed", "approval", "approved", "via", "using",
    "and", "qb", "sgov", "2025", "2026", "2027", "2028",
}

CASE_COLUMNS = [
    "Case_ID", "Rule_ID", "Risk_Tier", "Score", "Agency_Code", "Agency_Name",
    "Subject", "Pattern", "Period", "Boundary", "Total_Amount",
    "Excess_Above_Threshold", "Distinct_Buyers", "Reason_Overlap",
    "Category_Overlap", "Seller_Overlap", "Evidence_Order_IDs",
    "Evidence_Cart_IDs", "Evidence_Summary", "Score_Breakdown", "Rule_Version",
]


@dataclass(frozen=True)
class Settings:
    officer_cap: float = 6000.0
    refresh_window_days: int = 30
    cost_centre_threshold: float = 6000.0
    min_material_buyer_share: float = 0.10
    min_reason_shared_tokens: int = 2
    include_reason_check: bool = True


def _required(frame: pd.DataFrame, fields: list[str], name: str) -> None:
    missing = sorted(set(fields) - set(frame.columns))
    if missing:
        raise ValueError(f"{name}: missing required column(s): {', '.join(missing)}")


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = result.columns.str.strip()
    for col in result.columns:
        if pd.api.types.is_object_dtype(result[col]):
            result[col] = result[col].astype("string").str.strip()
    return result


def _optional(frame: pd.DataFrame, col: str, default: str = "") -> None:
    if col not in frame.columns:
        frame[col] = default


def _date_col(series: pd.Series) -> pd.Series:
    """Parse an entirely-serial, ISO, or day-first date column."""
    strings = series.astype("string").str.strip()
    numeric = pd.to_numeric(strings, errors="coerce")
    nonempty = strings.notna() & strings.ne("")
    if nonempty.any() and (numeric.notna() & nonempty).sum() / nonempty.sum() >= 0.95:
        dates = pd.to_datetime(numeric, unit="D", origin="1899-12-30", errors="coerce")
    else:
        dates = pd.to_datetime(strings, format="%Y-%m-%d", errors="coerce")
        unmatched = dates.isna() & nonempty
        if unmatched.any():
            dates.loc[unmatched] = pd.to_datetime(
                strings.loc[unmatched], format="%Y-%m-%d %H:%M:%S", errors="coerce"
            )
        unmatched = dates.isna() & nonempty
        if unmatched.any():
            dates.loc[unmatched] = pd.to_datetime(
                strings.loc[unmatched], dayfirst=True, errors="coerce"
            )
    return dates.dt.normalize()


def _true(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper().isin(["TRUE", "YES", "Y", "1"])


def _safe_str(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _token_set(text: Any) -> set[str]:
    return {
        tok for tok in re.findall(r"[a-z0-9]+", _safe_str(text).lower())
        if len(tok) >= 3 and tok not in STOPWORDS
    }


def _reason_shared(a: Any, b: Any, minimum: int) -> list[str]:
    shared = _token_set(a).intersection(_token_set(b))
    return sorted(shared) if len(shared) >= minimum else []


def _fiscal_period(dt: pd.Timestamp) -> str:
    fy = dt.year if dt.month >= 4 else dt.year - 1
    half = "H1" if 4 <= dt.month <= 9 else "H2"
    return f"FY{fy}-{half}"


def _fiscal_year(dt: pd.Timestamp) -> str:
    return _fiscal_period(dt).split("-")[0]


def _make_id(*parts: Any) -> str:
    digest = sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12].upper()
    return f"GL-{digest}"


def _unique_pipe(series: pd.Series) -> str:
    return " | ".join(sorted({_safe_str(v) for v in series if _safe_str(v)}))


def _band(score: int, *, priority: int, elevated: int, moderate: int) -> str:
    if score >= priority:
        return "High"
    if score >= elevated or score >= moderate:
        return "Medium"
    return "Low"


def _excess_score(excess: float) -> int:
    return min(3, max(0, math.ceil(round(excess, 2) / 1000.0)))


def normalize_qb_exports(
    invoices: pd.DataFrame, carts: pd.DataFrame, items: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Build order-level and item-level datasets from three QB CSV exports.

    Order totals are used ONLY once per Invoice_ID in G2B; line amounts are
    used ONLY at item grain in G2C. This prevents cart-seller/item fanout.
    """
    inv, cart, item = map(_clean, (invoices, carts, items))
    _required(inv, [
        "Invoice_ID", "Ref_Cart_ID", "Order_Date", "Total_Amt_Payable",
        "Buyer_Corporate_Email", "Agency_Code",
    ], "invoices")
    _required(cart, ["Cart_ID", "Reason_For_Purchase"], "carts")
    _required(item, ["Parent_Invoice_ID", "Product_Category", "Amount_After_Discount"], "items")
    for field in ["Buyer_Name", "Agency_Name", "Seller_Name", "Cost_Center", "Cost_Center_Description"]:
        _optional(inv, field)
    for field in [
        "Is_Cart_Cancelled", "Welfare_Purchase", "Costcenter_Code",
        "Approver_Corporate_Email", "Cart_Status", "Ecommerce_Cart_Created_On",
    ]:
        _optional(cart, field)
    for field in ["Invoice_Item_Cost_Centre_Code", "Item_Desc"]:
        _optional(item, field)
    item = item.reset_index(drop=True)
    item["Item_Row_Ref"] = item.index.astype(str)
    for field in ["Invoice_ID", "Ref_Cart_ID", "Agency_Code"]:
        if inv[field].isna().any() or inv[field].eq("").any():
            raise ValueError(f"invoices: {field} cannot be blank")
    if cart["Cart_ID"].isna().any() or cart["Cart_ID"].eq("").any():
        raise ValueError("carts: Cart_ID cannot be blank")
    inv = inv.drop_duplicates()
    cart = cart.drop_duplicates()
    if inv["Invoice_ID"].duplicated().any():
        raise ValueError("invoices: conflicting duplicate Invoice_ID; cannot safely total spend")
    if cart["Cart_ID"].duplicated().any():
        raise ValueError("carts: conflicting duplicate Cart_ID; cannot safely merge")
    inv["Order_Date"] = _date_col(inv["Order_Date"])
    inv["Total_Amt_Payable"] = pd.to_numeric(inv["Total_Amt_Payable"], errors="coerce")
    inv["Buyer_Corporate_Email"] = inv["Buyer_Corporate_Email"].str.lower()
    cart["Ecommerce_Cart_Created_On"] = _date_col(cart["Ecommerce_Cart_Created_On"])
    item["Amount_After_Discount"] = pd.to_numeric(item["Amount_After_Discount"], errors="coerce")
    invalid_invoices = inv[
        inv["Order_Date"].isna() | inv["Total_Amt_Payable"].isna() |
        (inv["Total_Amt_Payable"] <= 0) | inv["Buyer_Corporate_Email"].isna()
    ]
    if not invalid_invoices.empty:
        raise ValueError(f"invoices: {len(invalid_invoices)} row(s) with invalid date, amount or buyer")
    invalid_items = item["Amount_After_Discount"].isna() | (item["Amount_After_Discount"] <= 0)
    bad_items = int(invalid_items.sum())
    item = item.loc[~invalid_items].copy()
    unmatched_items = int((~item["Parent_Invoice_ID"].isin(inv["Invoice_ID"])).sum())
    item = item[item["Parent_Invoice_ID"].isin(inv["Invoice_ID"])].copy()
    cart["Cancelled"] = _true(cart["Is_Cart_Cancelled"])
    cart["Welfare"] = _true(cart["Welfare_Purchase"])
    # Governance Guide p.20: filter for 'approved' carts. A blank status means
    # the export did not supply the field (e.g. test fixtures), so it is kept.
    status = cart["Cart_Status"].fillna("").astype("string").str.strip().str.lower()
    cart["Not_Approved"] = status.ne("") & status.ne("approved")
    cart_cols = [
        "Cart_ID", "Reason_For_Purchase", "Costcenter_Code", "Approver_Corporate_Email",
        "Cart_Status", "Ecommerce_Cart_Created_On", "Cancelled", "Welfare", "Not_Approved",
    ]
    orders = inv.merge(
        cart[cart_cols], left_on="Ref_Cart_ID", right_on="Cart_ID", how="left",
        validate="many_to_one", indicator="_cart_match",
    )
    missing_carts = int((orders["_cart_match"] == "left_only").sum())
    orders["Cancelled"] = orders["Cancelled"].astype("boolean").fillna(False).astype(bool)
    cancelled_orders = int(orders["Cancelled"].sum())
    orders = orders[~orders["Cancelled"]].copy()
    orders["Not_Approved"] = orders["Not_Approved"].astype("boolean").fillna(False).astype(bool)
    non_approved_orders = int(orders["Not_Approved"].sum())
    orders = orders[~orders["Not_Approved"]].copy()
    orders["Welfare"] = orders["Welfare"].astype("boolean").fillna(False).astype(bool)
    orders["Event_Date"] = orders["Order_Date"]
    orders["Event_Date_Basis"] = "Order_Date"
    orders["Period"] = orders["Event_Date"].map(_fiscal_period)
    orders["FY"] = orders["Event_Date"].map(_fiscal_year)
    orders["Order_ID"] = orders["Invoice_ID"]
    orders["Cart_ID_Effective"] = orders["Ref_Cart_ID"]
    orders["Reason_For_Purchase"] = orders["Reason_For_Purchase"].fillna("")

    detail_cols = [
        "Order_ID", "Cart_ID_Effective", "Agency_Code", "Agency_Name", "Cost_Center",
        "Cost_Center_Description", "Buyer_Corporate_Email", "Buyer_Name",
        "Seller_Name", "Event_Date", "Period", "FY", "Reason_For_Purchase",
        "Welfare", "Approver_Corporate_Email",
    ]
    detail = item.merge(
        orders[detail_cols], left_on="Parent_Invoice_ID", right_on="Order_ID",
        how="inner", validate="many_to_one",
    )
    item_cc = detail["Invoice_Item_Cost_Centre_Code"].fillna("").astype("string").str.strip()
    invoice_cc = detail["Cost_Center"].fillna("").astype("string").str.strip()
    detail["Cost_Centre_Effective"] = item_cc.mask(item_cc.eq(""), invoice_cc)
    # Cart cost centre is only a fallback if the invoice has no cost centre.
    cart_cc_map = orders.set_index("Order_ID")["Costcenter_Code"].fillna("").to_dict()
    fallback = detail["Order_ID"].map(cart_cc_map).fillna("")
    detail["Cost_Centre_Effective"] = detail["Cost_Centre_Effective"].mask(
        detail["Cost_Centre_Effective"].eq(""), fallback
    )
    quality = {
        "invoice_rows_loaded": len(inv),
        "cart_rows_loaded": len(cart),
        "item_rows_loaded": len(items),
        "unmatched_invoice_cart_rows": missing_carts,
        "cancelled_orders_excluded": cancelled_orders,
        "non_approved_orders_excluded": non_approved_orders,
        "invalid_or_nonpositive_items_excluded": bad_items,
        "items_without_invoice_excluded": unmatched_items,
        "orders_without_item_rows": int((~orders["Order_ID"].isin(detail["Order_ID"])).sum()),
        "missing_item_cost_centres": int(detail["Cost_Centre_Effective"].fillna("").eq("").sum()),
        "event_date_basis": "Order_Date (Invoices file)",
        "order_rows_ready": len(orders),
        "item_rows_ready": len(detail),
    }
    return orders.reset_index(drop=True), detail.reset_index(drop=True), quality


def _blank_record() -> dict[str, Any]:
    return {key: "" for key in CASE_COLUMNS}


def detect_g2b(orders: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """One case per agency/officer/reset boundary, NOT per invoice or line."""
    if orders.empty:
        return pd.DataFrame(columns=CASE_COLUMNS)
    base = orders[~orders["Welfare"]].copy()
    if base.empty:
        return pd.DataFrame(columns=CASE_COLUMNS)
    first, last = base["Event_Date"].min(), base["Event_Date"].max()
    boundaries = [
        pd.Timestamp(year, month, 1)
        for year in range(first.year - 1, last.year + 2)
        for month in (4, 10)
    ]
    cases: list[dict[str, Any]] = []
    for agency_buyer, by_buyer in base.groupby(
        ["Agency_Code", "Buyer_Corporate_Email"], dropna=False
    ):
        agency, buyer = agency_buyer
        for boundary in boundaries:
            pre = by_buyer[
                (by_buyer["Event_Date"] >= boundary - timedelta(days=settings.refresh_window_days)) &
                (by_buyer["Event_Date"] < boundary)
            ]
            post = by_buyer[
                (by_buyer["Event_Date"] >= boundary) &
                (by_buyer["Event_Date"] < boundary + timedelta(days=settings.refresh_window_days))
            ]
            if pre.empty or post.empty:
                continue
            pre_spend = round(float(pre["Total_Amt_Payable"].sum()), 2)
            post_spend = round(float(post["Total_Amt_Payable"].sum()), 2)
            total = round(pre_spend + post_spend, 2)
            if total <= settings.officer_cap:
                continue
            categories_pre = set()
            categories_post = set()
            # Categories are collected from invoice item rows by the caller below.
            # Base orders carry the Category_Set column, attached in analyse().
            for v in pre["Category_Set"]:
                categories_pre.update(v)
            for v in post["Category_Set"]:
                categories_post.update(v)
            shared_cats = sorted(categories_pre & categories_post)
            shared_sellers = sorted(set(pre["Seller_Name"].dropna()) & set(post["Seller_Name"].dropna()))
            best_shared: list[str] = []
            best_pair: tuple[str, str] | None = None
            corroborated_pair = False
            for _, p in pre.iterrows():
                for _, q in post.iterrows():
                    shared = _reason_shared(
                        p["Reason_For_Purchase"], q["Reason_For_Purchase"],
                        settings.min_reason_shared_tokens,
                    )
                    # A high-priority override needs category AND reason
                    # evidence from the SAME pair of cross-boundary orders.
                    same_pair_category = bool(p["Category_Set"] & q["Category_Set"])
                    corroborated_pair |= bool(shared and same_pair_category)
                    if len(shared) > len(best_shared):
                        best_shared = shared
                        best_pair = (_safe_str(p["Order_ID"]), _safe_str(q["Order_ID"]))
            excess = round(total - settings.officer_cap, 2)
            s1 = _excess_score(excess)
            s2 = 3 if shared_cats else 0
            s3 = 2 if best_shared else 0
            score = s1 + s2 + s3
            priority_override = corroborated_pair
            tier = "High" if priority_override else _band(
                score, priority=10, elevated=6, moderate=3
            )
            linked = pd.concat([pre, post], ignore_index=True)
            name = _safe_str(linked["Buyer_Name"].dropna().iloc[0]) if linked["Buyer_Name"].notna().any() else buyer
            summary = (
                f"${pre_spend:,.2f} before and ${post_spend:,.2f} after "
                f"{boundary.date()} (combined ${total:,.2f}; excess over review threshold "
                f"${excess:,.2f}). "
                f"Shared categories: {', '.join(shared_cats) or 'none established'}. "
                f"Shared meaningful reason tokens: {', '.join(best_shared) or 'none established'}."
            )
            row = _blank_record()
            row.update({
                "Case_ID": _make_id("G2B", agency, buyer, boundary.date()),
                "Rule_ID": "G2B", "Risk_Tier": tier, "Score": score,
                "Agency_Code": agency, "Agency_Name": _safe_str(linked["Agency_Name"].iloc[0]),
                "Subject": f"{name} ({buyer})", "Pattern": "Spend spanning QB cap reset",
                "Period": _fiscal_year(boundary), "Boundary": str(boundary.date()),
                "Total_Amount": total, "Excess_Above_Threshold": excess,
                "Distinct_Buyers": 1, "Reason_Overlap": ", ".join(best_shared),
                "Category_Overlap": ", ".join(shared_cats),
                "Seller_Overlap": ", ".join(shared_sellers),
                "Evidence_Order_IDs": _unique_pipe(linked["Order_ID"]),
                "Evidence_Cart_IDs": _unique_pipe(linked["Cart_ID_Effective"]),
                "Evidence_Summary": summary + (f" Strongest reason pair: {best_pair}." if best_pair else ""),
                "Score_Breakdown": f"excess={s1}; common_category={s2}; reason_overlap={s3}",
                "Rule_Version": RULE_VERSION,
            })
            cases.append(row)
    result = pd.DataFrame(cases, columns=CASE_COLUMNS)
    if result.empty:
        return result
    # Repeat boundaries are scored using the same agency+officer identity.
    # Agency+buyer is embedded in each case ID, but Subject may include a
    # mutable display name. Resolve the original buyer email from Subject.
    result["_buyer_key"] = result["Subject"].str.extract(r"\(([^()]+@[^()]+)\)$")[0]
    for (_, _), grp in result.groupby(["Agency_Code", "_buyer_key"]):
        bump = max(0, len(grp) - 1) * 2
        if bump:
            result.loc[grp.index, "Score"] += bump
            result.loc[grp.index, "Score_Breakdown"] += f"; repeat_boundary={bump}"
    for idx, row in result.iterrows():
        if row["Risk_Tier"] != "High":
            result.at[idx, "Risk_Tier"] = _band(
                int(row["Score"]), priority=10, elevated=6, moderate=3
            )
    return result.drop(columns="_buyer_key")


def _g2c_group(group: pd.DataFrame, settings: Settings, key: tuple[Any, ...]) -> dict[str, Any] | None:
    agency, cc, category, period = key
    amount_by_buyer = group.groupby("Buyer_Corporate_Email")["Amount_After_Discount"].sum()
    total = round(float(amount_by_buyer.sum()), 2)
    if len(amount_by_buyer) < 2 or total <= settings.cost_centre_threshold:
        return None
    shares = amount_by_buyer / total
    # Existing triage script excludes buyers contributing <=10% from the
    # corroborating material total. At least two must remain above the cap.
    material = shares[shares > settings.min_material_buyer_share].index.tolist()
    material_total = round(float(amount_by_buyer.loc[material].sum()), 2)
    if len(material) < 2 or material_total <= settings.cost_centre_threshold:
        return None
    group = group[group["Buyer_Corporate_Email"].isin(material)].copy()
    distinct_orders = group.drop_duplicates("Order_ID").sort_values("Event_Date")
    gaps = distinct_orders["Event_Date"].diff().dt.days
    avg_gap = float(gaps.mean()) if gaps.notna().any() else None
    same_day_seller = False
    best_shared: list[str] = []
    same_day_shared_pair = False
    buyer_reasons = distinct_orders[[
        "Buyer_Corporate_Email", "Reason_For_Purchase", "Seller_Name", "Event_Date"
    ]].to_dict("records")
    for ix, p in enumerate(buyer_reasons):
        for q in buyer_reasons[ix + 1:]:
            if p["Buyer_Corporate_Email"] == q["Buyer_Corporate_Email"]:
                continue
            shared = _reason_shared(
                p["Reason_For_Purchase"], q["Reason_For_Purchase"],
                settings.min_reason_shared_tokens,
            )
            same_day_same_seller = (
                p["Event_Date"] == q["Event_Date"] and
                pd.notna(p["Seller_Name"]) and p["Seller_Name"] == q["Seller_Name"]
            )
            same_day_seller |= same_day_same_seller
            same_day_shared_pair |= bool(same_day_same_seller and shared)
            if len(shared) > len(best_shared):
                best_shared = shared
    s1 = 3 if avg_gap is not None and avg_gap < 1 else (
        2 if avg_gap is not None and avg_gap <= 30 else (1 if avg_gap is not None else 0)
    )
    s2 = 3 if best_shared else 0
    excess = round(material_total - settings.cost_centre_threshold, 2)
    s3 = _excess_score(excess)
    s4 = max(0, len(material) - 2)
    score = s1 + s2 + s3 + s4
    override = same_day_shared_pair and len(material) >= 3
    tier = "High" if override else _band(score, priority=10, elevated=6, moderate=3)
    subject = f"{cc} / {category}"
    summary = (
        f"{len(material)} material buyers collectively purchased ${material_total:,.2f} "
        f"in {period}, excess ${excess:,.2f} above the screening threshold. "
        f"Average gap between unique orders: "
        f"{f'{avg_gap:.1f} days' if avg_gap is not None else 'not available'}. "
        f"Same-day/same-seller: {'yes' if same_day_seller else 'no'}. "
        f"Shared meaningful reason tokens: {', '.join(best_shared) or 'none established'}."
    )
    row = _blank_record()
    row.update({
        "Case_ID": _make_id("G2C", agency, cc, category, period),
        "Rule_ID": "G2C", "Risk_Tier": tier, "Score": score,
        "Agency_Code": agency, "Agency_Name": _safe_str(group["Agency_Name"].iloc[0]),
        "Subject": subject, "Pattern": "Multiple buyers in cost centre and category",
        "Period": period, "Boundary": "", "Total_Amount": material_total,
        "Excess_Above_Threshold": excess, "Distinct_Buyers": len(material),
        "Reason_Overlap": ", ".join(best_shared),
        "Category_Overlap": category, "Seller_Overlap": "same day/seller" if same_day_seller else "",
        "Evidence_Order_IDs": _unique_pipe(group["Order_ID"]),
        "Evidence_Cart_IDs": _unique_pipe(group["Cart_ID_Effective"]),
        "Evidence_Summary": summary,
        "Score_Breakdown": f"timing={s1}; reason_overlap={s2}; excess={s3}; extra_buyers={s4}",
        "Rule_Version": RULE_VERSION,
    })
    return row


def detect_g2c(detail: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=CASE_COLUMNS)
    base = detail[
        ~detail["Welfare"] & detail["Cost_Centre_Effective"].notna() &
        detail["Cost_Centre_Effective"].ne("") &
        detail["Product_Category"].notna() & detail["Product_Category"].ne("")
    ].copy()
    cases = []
    for key, group in base.groupby(
        ["Agency_Code", "Cost_Centre_Effective", "Product_Category", "Period"],
        dropna=False,
    ):
        case = _g2c_group(group, settings, key)
        if case is not None:
            cases.append(case)
    result = pd.DataFrame(cases, columns=CASE_COLUMNS)
    if result.empty:
        return result
    # Add historical recurrence only for multiple flagged half-FY periods.
    for (_, subject), grp in result.groupby(["Agency_Code", "Subject"]):
        if grp["Period"].nunique() > 1:
            result.loc[grp.index, "Score"] += 2
            result.loc[grp.index, "Score_Breakdown"] += "; repeat_period=2"
    for idx, row in result.iterrows():
        if row["Risk_Tier"] != "High":
            result.at[idx, "Risk_Tier"] = _band(
                int(row["Score"]), priority=10, elevated=6, moderate=3
            )
    return result


# Governance Guide p.20 examples and keywords. Deliberately broad: the PoC
# accepts more false alarms in exchange for not missing vague reasons.
GENERIC_REASONS = {
    "", "qb buy", "purchase", "buy items", "items", "misc", "miscellaneous",
    "general purchase", "for office use", "office use", "as discussed",
    "qb transaction for approval pls", "office supplies", "general office supplies",
    "office general supplies", "for operations", "for operations use", "operations",
    "events", "for events", "others", "other supplies", "supplies", "nil", "na",
    "n/a", "-", "test", "testing",
}
QB_LABEL = re.compile(
    r"^(?:qb|bq|quick\s*buy|quickbuy)\s*(?:20\d{2})?\s*"
    r"(?:buy|purchase|transaction|order|items?)?\s*(?:for\s+approval)?\s*(?:pls|please)?$"
)
OFFLINE_KEYWORDS = re.compile(
    r"\b(?:offline|e-?mails?|e-?mailed|refer|referred|referring|as\s+discussed|"
    r"approve|approved|approval|approvals)\b"
)
GENERIC_WORDS = {
    "office", "general", "supplies", "supply", "items", "item", "stuff", "things",
    "misc", "miscellaneous", "use", "used", "operations", "operation", "operational",
    "events", "event", "others", "other", "stock", "stocks", "quickbuy", "quick",
    "transaction", "pls", "please", "works", "work",
}


def classify_reason(reason: Any) -> tuple[bool, bool, list[str]]:
    """Return (vague, offline_reference, matched_keywords) for a purchase reason."""
    text = _safe_str(reason)
    cleaned = re.sub(r"\s+", " ", text.lower()).strip(" .,!")
    keywords = sorted({m.group(0) for m in OFFLINE_KEYWORDS.finditer(cleaned)})
    meaningful = [
        tok for tok in re.findall(r"[a-z0-9]+", cleaned)
        if len(tok) >= 3 and tok not in STOPWORDS and tok not in GENERIC_WORDS
        and not tok.isdigit() and not re.fullmatch(r"(?:qb|bq)\d*", tok)
    ]
    has_hashtag = "#" in cleaned
    vague = (
        cleaned in GENERIC_REASONS or bool(QB_LABEL.match(cleaned))
        or (len(set(meaningful)) < 2 and not has_hashtag)
    )
    return vague, bool(keywords), keywords


def detect_reasons(orders: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Third QB-native check (Governance Guide p.20): vague reasons and offline-approval keywords."""
    if orders.empty or not settings.include_reason_check:
        return pd.DataFrame(columns=CASE_COLUMNS)
    cases = []
    for cart_id, group in orders.groupby("Cart_ID_Effective"):
        # Absent cart exports do not prove that the buyer gave a blank reason.
        if group["_cart_match"].ne("both").all():
            continue
        reason = _safe_str(group["Reason_For_Purchase"].iloc[0])
        vague, offline, keywords = classify_reason(reason)
        if not (vague or offline):
            continue
        row = _blank_record()
        first = group.iloc[0]
        if vague and offline:
            label = "Vague reason and possible offline approval reference"
        elif offline:
            label = "Possible offline approval reference"
        else:
            label = "Uninformative purchase reason"
        score = 2 * int(offline) + int(vague)
        row.update({
            "Case_ID": _make_id("REASON", first["Agency_Code"], cart_id),
            "Rule_ID": "REASON", "Risk_Tier": "Medium" if offline else "Low",
            "Score": score,
            "Agency_Code": first["Agency_Code"], "Agency_Name": first["Agency_Name"],
            "Subject": f"Cart {cart_id}", "Pattern": label,
            "Period": first["FY"], "Boundary": "",
            "Total_Amount": round(float(group["Total_Amt_Payable"].sum()), 2),
            "Excess_Above_Threshold": 0, "Distinct_Buyers": 1,
            "Reason_Overlap": ", ".join(keywords), "Category_Overlap": "", "Seller_Overlap": "",
            "Evidence_Order_IDs": _unique_pipe(group["Order_ID"]),
            "Evidence_Cart_IDs": str(cart_id),
            "Evidence_Summary": (
                f"Recorded reason: {reason!r}. Pattern: {label}."
                + (f" Keywords matched: {', '.join(keywords)}." if keywords else "")
                + " Manual context required."
            ),
            "Score_Breakdown": f"vague={int(vague)}; offline_reference={int(offline)}",
            "Rule_Version": RULE_VERSION,
        })
        cases.append(row)
    return pd.DataFrame(cases, columns=CASE_COLUMNS)


def analyse(
    invoices: pd.DataFrame, carts: pd.DataFrame, items: pd.DataFrame,
    settings: Settings = Settings(),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return unified review queue, canonical orders/items, and data quality."""
    orders, detail, quality = normalize_qb_exports(invoices, carts, items)
    category_lookup = (
        detail.groupby("Order_ID")["Product_Category"]
        .agg(lambda values: frozenset(v for v in values if pd.notna(v) and v != ""))
        .to_dict()
    ) if not detail.empty else {}
    orders["Category_Set"] = orders["Order_ID"].map(
        lambda order_id: category_lookup.get(order_id, frozenset())
    )
    parts = [
        detect_g2b(orders, settings),
        detect_g2c(detail, settings),
        detect_reasons(orders, settings),
    ]
    nonempty = [part for part in parts if not part.empty]
    all_cases = pd.concat(nonempty, ignore_index=True) if nonempty else pd.DataFrame(columns=CASE_COLUMNS)
    if not all_cases.empty:
        all_cases["_risk_rank"] = all_cases["Risk_Tier"].map({"High": 0, "Medium": 1, "Low": 2})
        all_cases = (all_cases.sort_values(
            ["_risk_rank", "Score", "Total_Amount"], ascending=[True, False, False]
        ).drop(columns="_risk_rank").reset_index(drop=True))
    return all_cases, orders, detail, quality


def case_orders(case: pd.Series, orders: pd.DataFrame) -> pd.DataFrame:
    ids = {v.strip() for v in str(case["Evidence_Order_IDs"]).split("|") if v.strip()}
    return orders[orders["Order_ID"].isin(ids)].sort_values("Event_Date").copy()


def case_items(case: pd.Series, items: pd.DataFrame) -> pd.DataFrame:
    ids = {v.strip() for v in str(case["Evidence_Order_IDs"]).split("|") if v.strip()}
    return items[items["Order_ID"].isin(ids)].copy()
