"""Data sources for QB GovLens.

* load_masked_sample(): the masked QB Admin Portal exports in demo_data/
  (Carts, Invoices, InvoiceItems), used as the app's built-in dataset.
* create_demo(): small fictitious rule-test scenarios, used only by the unit tests.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "demo_data"
SAMPLE_FILES = {
    "invoices": "all_qbpurchase_invoice.csv",
    "carts": "all_qbpurchase_carts.csv",
    "items": "all_qbpurchase_invoiceitems.csv",
}


def load_masked_sample(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (invoices, carts, items) from the masked sample exports."""
    frames = []
    for key in ("invoices", "carts", "items"):
        path = Path(data_dir) / SAMPLE_FILES[key]
        if not path.exists():
            raise FileNotFoundError(f"Masked sample file not found: {path}")
        frames.append(pd.read_csv(path, dtype="string", encoding="utf-8-sig"))
    return frames[0], frames[1], frames[2]


def create_demo() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (invoices, carts, items); all identities and purchases fictitious."""
    purchases = [
        # Genuine-looking continuing need across the April 2026 cap reset.
        ("INV001", "CART001", "2026-03-20", 3300, "ava@example.test", "Ava Lee", "AG1", "Demo Education Agency", "Supplier A", "CC-LAB", "Laboratories", "robotics demonstration kits for school workshop", "Teaching Equipment", 3300, "robotics demonstration kit", False, False),
        ("INV002", "CART002", "2026-04-04", 3400, "ava@example.test", "Ava Lee", "AG1", "Demo Education Agency", "Supplier A", "CC-LAB", "Laboratories", "additional robotics demonstration kits for school workshop", "Teaching Equipment", 3400, "robotics demonstration kit", False, False),
        # Same period, 3 different buyers, same seller, reason overlap -> G2C High.
        ("INV003", "CART003", "2026-05-08", 2450, "ben@example.test", "Ben Lim", "AG1", "Demo Education Agency", "Supplier B", "CC-TRAIN", "Training", "digital literacy workshop learning packs cohort one", "Training Materials", 2450, "learning packs", False, False),
        ("INV004", "CART004", "2026-05-08", 2400, "cora@example.test", "Cora Ng", "AG1", "Demo Education Agency", "Supplier B", "CC-TRAIN", "Training", "digital literacy workshop learning packs cohort two", "Training Materials", 2400, "learning packs", False, False),
        ("INV005", "CART005", "2026-05-08", 1800, "dan@example.test", "Dan Tan", "AG1", "Demo Education Agency", "Supplier B", "CC-TRAIN", "Training", "digital literacy workshop learning packs cohort three", "Training Materials", 1800, "learning packs", False, False),
        # Non-material buyer: excluded from G2C materially corroborating spend.
        ("INV006", "CART006", "2026-05-10", 80, "erin@example.test", "Erin Koh", "AG1", "Demo Education Agency", "Supplier B", "CC-TRAIN", "Training", "refresh snacks for digital literacy workshop", "Training Materials", 80, "refreshments", False, False),
        # A low-evidence boundary straddle: unrelated categories/reasons.
        ("INV007", "CART007", "2026-09-28", 3200, "fay@example.test", "Fay Ong", "AG1", "Demo Education Agency", "Supplier C", "CC-OPS", "Operations", "replacement printer toner cartridges", "Office Consumables", 3200, "printer toner", False, False),
        ("INV008", "CART008", "2026-10-02", 3400, "fay@example.test", "Fay Ong", "AG1", "Demo Education Agency", "Supplier D", "CC-OPS", "Operations", "engineering measuring calipers", "Equipment", 3400, "measuring calipers", False, False),
        # Vague reason and offline approval reference, without G2B / G2C.
        ("INV009", "CART009", "2026-06-03", 150, "gil@example.test", "Gil Teo", "AG1", "Demo Education Agency", "Supplier C", "CC-OPS", "Operations", "QB buy", "Stationery", 150, "pen set", False, False),
        ("INV010", "CART010", "2026-06-04", 260, "hue@example.test", "Hue Tan", "AG1", "Demo Education Agency", "Supplier C", "CC-OPS", "Operations", "approved via email for event banners", "Signage", 260, "event banners", False, False),
        # Cancelled and welfare: should not raise G2B/G2C cases.
        ("INV011", "CART011", "2026-05-08", 5900, "ian@example.test", "Ian Tan", "AG1", "Demo Education Agency", "Supplier B", "CC-TRAIN", "Training", "digital literacy workshop learning packs", "Training Materials", 5900, "learning packs", False, True),
        ("INV012", "CART012", "2026-05-08", 6000, "jan@example.test", "Jan Leong", "AG1", "Demo Education Agency", "Supplier B", "CC-TRAIN", "Training", "digital literacy workshop learning packs", "Training Materials", 6000, "learning packs", True, False),
        # Same cost-centre code in a DIFFERENT agency must not mix.
        ("INV013", "CART013", "2026-05-08", 5900, "kai@example.test", "Kai Lim", "AG2", "Demo Transport Agency", "Supplier B", "CC-TRAIN", "Training", "digital literacy workshop learning packs", "Training Materials", 5900, "learning packs", False, False),
        # Multi-invoice cart (two seller orders): no order/invoice fanout.
        ("INV014", "CART014", "2026-07-14", 110, "lee@example.test", "Lee Ong", "AG2", "Demo Transport Agency", "Supplier C", "CC-TECH", "Technology", "replacement cable adapters", "Electronics", 110, "adapters", False, False),
        ("INV015", "CART014", "2026-07-14", 140, "lee@example.test", "Lee Ong", "AG2", "Demo Transport Agency", "Supplier D", "CC-TECH", "Technology", "replacement cable adapters", "Electronics", 140, "cables", False, False),
    ]
    cols = [
        "Invoice_ID", "Ref_Cart_ID", "Order_Date", "Total_Amt_Payable",
        "Buyer_Corporate_Email", "Buyer_Name", "Agency_Code", "Agency_Name",
        "Seller_Name", "Cost_Center", "Cost_Center_Description",
        "Reason_For_Purchase", "Product_Category", "Item_Amount",
        "Item_Desc", "Welfare_Purchase", "Is_Cart_Cancelled",
    ]
    data = pd.DataFrame(purchases, columns=cols)
    inv = data[[
        "Invoice_ID", "Ref_Cart_ID", "Order_Date", "Total_Amt_Payable",
        "Buyer_Corporate_Email", "Buyer_Name", "Agency_Code", "Agency_Name",
        "Seller_Name", "Cost_Center", "Cost_Center_Description",
    ]].copy()
    carts = data[[
        "Ref_Cart_ID", "Reason_For_Purchase", "Welfare_Purchase", "Is_Cart_Cancelled",
        "Cost_Center",
    ]].drop_duplicates("Ref_Cart_ID").rename(columns={
        "Ref_Cart_ID": "Cart_ID", "Cost_Center": "Costcenter_Code",
    }).copy()
    carts["Approver_Corporate_Email"] = "ao@example.test"
    # Leave submission time unavailable to test historical order-date fallback.
    items = data[["Invoice_ID", "Product_Category", "Item_Amount", "Item_Desc", "Cost_Center"]].rename(columns={
        "Invoice_ID": "Parent_Invoice_ID", "Item_Amount": "Amount_After_Discount",
        "Cost_Center": "Invoice_Item_Cost_Centre_Code",
    }).copy()
    return inv, carts, items
