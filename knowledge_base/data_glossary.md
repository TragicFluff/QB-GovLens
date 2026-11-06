# QB Admin Portal Data Glossary (curated knowledge base)

doc: DG
source_document: Data Glossary of QB Admin Portal Data (Headers).xlsx
source_version: Data glossary last updated on 12 December 2025
curation_note: Descriptions copied verbatim for the fields QB GovLens reads, grouped by topic.

## [DG-JOIN-KEYS] Identifiers used to link carts, invoices and invoice items
page: sheets Carts, InvoiceItems, Invoices

- Carts dataset, Cart_ID: Unique Cart ID number
- Invoices dataset, Invoice_ID: Unique invoice ID
- Invoices dataset, Ref_Cart_ID: Unique cart ID
- Invoices dataset, Ref_Order_ID: Unique order ID
- InvoiceItems dataset, Invoice_Item_ID: Unique invoice item ID
- InvoiceItems dataset, Parent_Invoice_ID: Unique parent invoice ID

## [DG-CART-PURPOSE] Reason for purchase and welfare indicator
page: sheets Carts, InvoiceItems

- Carts dataset, Reason_For_Purchase: Remarks indicated by buyer to justify purchase
- Carts dataset, Welfare_Purchase: Indicator for when a purchase is detected to be a welfare purchase, based on whether #welfare was included in the reason for purchase that buyer has provided i.e., True = #welfare was used in reason for purchase, False = #welfare not used in reason for purchase
- InvoiceItems dataset, Welfare_Purchase: Indicator for when a purchase is detected to be a welfare purchase, based on whether #welfare was included in the reason for purchase that buyer has provided i.e., True = #welfare was used in reason for purchase, False = #welfare not used in reason for purchase

## [DG-CART-STATUS-TIMING] Cart status, cancellation, approval and cart timestamps
page: sheets Carts

- Carts dataset, Cart_Status: Status of cart i.e. pending submission, approved, rejected, expired
- Carts dataset, Is_Cart_Cancelled: Status to indicate if the ecommerce cart has been cancelled i.e. True = Cart has been cancelled by buyer or ecommerce, False = Cart has not been cancelled by buyer or ecommerce
- Carts dataset, Ecommerce_Cart_Created_On: Timestamp for when buyer created the ecommerce cart
- Carts dataset, Cart_Created_On: Timestamp for ecommerce cart creation
- Carts dataset, Cart_Approved_On: Timestamp where cart was approved
- Carts dataset, Approver_Corporate_Email: Work email address of approver
- Carts dataset, Approver_Remarks: Reason provided by approver for rejecting the cart

## [DG-BUYER-SELLER] Agency, buyer and seller fields
page: sheets Invoices

- Invoices dataset, Agency_Code: Agency code of buyer e.g. MOF
- Invoices dataset, Agency_Name: Agency name of buyer e.g., Ministry of Finance
- Invoices dataset, Buyer_Corporate_Email: Work email address of buyer
- Invoices dataset, Buyer_Name: Name of buyer
- Invoices dataset, Ecommerce_Name: Name of ecommerce that buyer purchased from
- Invoices dataset, Seller_Name: Name of ecommerce seller

## [DG-INVOICE-DATES-AMOUNTS] Order dates and invoice-level amounts
page: sheets Carts, Invoices

- Invoices dataset, Order_Date: Timestamp where order was placed
- Invoices dataset, Invoice_Date: Timestamp when buyer is invoiced by ecommerce
- Invoices dataset, Subtotal: Subtotal amount
- Invoices dataset, Additional_Discount: Reflects any additional discount
- Invoices dataset, Shipping_Fee: Shipping fee
- Invoices dataset, GST_Amt: GST amount
- Invoices dataset, Total_Amt_Payable: Total amount payable
- Carts dataset, Total_Amt_Payable: Total amount payable

## [DG-COST-CENTRE] Cost centre and account code fields
page: sheets Carts, InvoiceItems, Invoices

- Carts dataset, Costcenter_Code: Cost center code selected by buyer for purchase
- Carts dataset, Costcenter_Description: Description of cost centre selected by buyer for purchase
- Invoices dataset, Costcenter_Code: Cost center code selected by buyer for purchase
- InvoiceItems dataset, Invoice_Item_Cost_Centre_Code: Cost centre that the invoice item has been charged to
- InvoiceItems dataset, Invoice_Item_Cost_Centre_Code_Description: Cost centre code description
- InvoiceItems dataset, Invoice_Item_Account_Code: Account code autopopulated for invoice item, based on the pre-mapped product category and account code

## [DG-ITEM-DESCRIPTION] Item description and product category
page: sheets InvoiceItems

- InvoiceItems dataset, Item_Desc: Product description from ecommerce
- InvoiceItems dataset, Item_Desc_Details: Product description details from ecommerce
- InvoiceItems dataset, Product_Category: Product category from ecommerce

## [DG-ITEM-PRICE-QTY] Item unit price, quantity and amounts
page: sheets InvoiceItems

- InvoiceItems dataset, Unit_Price: Unit price of order item
- InvoiceItems dataset, Qty: Quantity of item purchased
- InvoiceItems dataset, Amount_Before_Discount: Amount before discount
- InvoiceItems dataset, Item_Discount: Discount offered by ecommerce
- InvoiceItems dataset, Amount_After_Discount: Amount after discount
- InvoiceItems dataset, Invoice_Item_Created_On: Timestamp for invoice item creation
