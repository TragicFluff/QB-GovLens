"""Rebuild knowledge_base/data_glossary.md from the official QB Data Glossary (.xlsx).

Usage (from the app folder):
    python scripts/build_glossary_kb.py "demo_data/Data Glossary of QB Admin Portal Data (Headers).xlsx"

Descriptions are copied VERBATIM from the glossary. Only the fields that QB GovLens
reads are kept, grouped into topical passages so each retrieved passage is
self-contained. The Change History sheet is deliberately not ingested.
Requires: openpyxl (pip install openpyxl). Not needed to run the app itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import load_workbook

# (citation id, title, [(sheet, header), ...])
GROUPS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("DG-JOIN-KEYS", "Identifiers used to link carts, invoices and invoice items", [
        ("Carts", "Cart_ID"), ("Invoices", "Invoice_ID"), ("Invoices", "Ref_Cart_ID"),
        ("Invoices", "Ref_Order_ID"), ("InvoiceItems", "Invoice_Item_ID"),
        ("InvoiceItems", "Parent_Invoice_ID"),
    ]),
    ("DG-CART-PURPOSE", "Reason for purchase and welfare indicator", [
        ("Carts", "Reason_For_Purchase"), ("Carts", "Welfare_Purchase"),
        ("InvoiceItems", "Welfare_Purchase"),
    ]),
    ("DG-CART-STATUS-TIMING", "Cart status, cancellation, approval and cart timestamps", [
        ("Carts", "Cart_Status"), ("Carts", "Is_Cart_Cancelled"),
        ("Carts", "Ecommerce_Cart_Created_On"), ("Carts", "Cart_Created_On"),
        ("Carts", "Cart_Approved_On"), ("Carts", "Approver_Corporate_Email"),
        ("Carts", "Approver_Remarks"),
    ]),
    ("DG-BUYER-SELLER", "Agency, buyer and seller fields", [
        ("Invoices", "Agency_Code"), ("Invoices", "Agency_Name"),
        ("Invoices", "Buyer_Corporate_Email"), ("Invoices", "Buyer_Name"),
        ("Invoices", "Ecommerce_Name"), ("Invoices", "Seller_Name"),
    ]),
    ("DG-INVOICE-DATES-AMOUNTS", "Order dates and invoice-level amounts", [
        ("Invoices", "Order_Date"), ("Invoices", "Invoice_Date"),
        ("Invoices", "Subtotal"), ("Invoices", "Additional_Discount"),
        ("Invoices", "Shipping_Fee"), ("Invoices", "GST_Amt"),
        ("Invoices", "Total_Amt_Payable"), ("Carts", "Total_Amt_Payable"),
    ]),
    ("DG-COST-CENTRE", "Cost centre and account code fields", [
        ("Carts", "Costcenter_Code"), ("Carts", "Costcenter_Description"),
        ("Invoices", "Costcenter_Code"), ("InvoiceItems", "Invoice_Item_Cost_Centre_Code"),
        ("InvoiceItems", "Invoice_Item_Cost_Centre_Code_Description"),
        ("InvoiceItems", "Invoice_Item_Account_Code"),
    ]),
    ("DG-ITEM-DESCRIPTION", "Item description and product category", [
        ("InvoiceItems", "Item_Desc"), ("InvoiceItems", "Item_Desc_Details"),
        ("InvoiceItems", "Product_Category"),
    ]),
    ("DG-ITEM-PRICE-QTY", "Item unit price, quantity and amounts", [
        ("InvoiceItems", "Unit_Price"), ("InvoiceItems", "Qty"),
        ("InvoiceItems", "Amount_Before_Discount"), ("InvoiceItems", "Item_Discount"),
        ("InvoiceItems", "Amount_After_Discount"), ("InvoiceItems", "Invoice_Item_Created_On"),
    ]),
]


def read_sheet(ws) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        header, desc = (row + (None, None))[:2]
        if header and desc:
            out[str(header).strip()] = " ".join(str(desc).split())
    return out


def main(xlsx: str, out_path: str = "knowledge_base/data_glossary.md") -> None:
    wb = load_workbook(xlsx, data_only=True)
    sheets = {name.strip(): read_sheet(wb[name]) for name in wb.sheetnames
              if name.strip() in {"Carts", "Invoices", "InvoiceItems"}}
    lines = [
        "# QB Admin Portal Data Glossary (curated knowledge base)",
        "",
        "doc: DG",
        "source_document: Data Glossary of QB Admin Portal Data (Headers).xlsx",
        "source_version: Data glossary last updated on 12 December 2025",
        "curation_note: Descriptions copied verbatim for the fields QB GovLens reads, grouped by topic.",
        "",
    ]
    missing = []
    for cid, title, fields in GROUPS:
        body = []
        for sheet, header in fields:
            desc = sheets.get(sheet, {}).get(header)
            if desc is None:
                missing.append(f"{sheet}.{header}")
                continue
            body.append(f"- {sheet} dataset, {header}: {desc}")
        page = "sheets " + ", ".join(sorted({s for s, _ in fields}))
        lines += [f"## [{cid}] {title}", f"page: {page}", "", *body, ""]
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}" + (f"; not found in glossary: {missing}" if missing else ""))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:])
