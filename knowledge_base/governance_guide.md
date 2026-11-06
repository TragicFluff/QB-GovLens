# QB Admin Portal Governance Guide for Agencies (curated knowledge base)

doc: GG
source_document: QB Admin Portal Governance Guide for Agencies (Ministry of Finance and GovTech)
curation_note: Text transcribed from the official guide, one passage per governance check or data topic, with PDF extraction errors corrected. Portal navigation and screenshot pages (icons, filters, download steps) are summarised in a single passage. Wording is otherwise kept as in the guide.

## [GG-PURPOSE] Purpose of the guide: structured QB data for SVP governance
page: 2

QuickBuy@SGov (QB) Admin Portal captures QB transactional data in structured format. This is in contrast with the alternative channel for Small Value Purchases (SVP) of buy-and-claim where transactional data are often captured in the form of unstructured format (e.g., images of receipts).

When there is data visibility and seamless access to structured data, officers can perform meaningful analysis to glean insights (e.g., potential anomalies, purchasing patterns) to guide decision-making.

This guide aims to inform users on how they can: (a) navigate the portal through features like icons and filters to readily access and download transactional data; (b) enhance effectiveness and efficiency in their analysis process by understanding how to interpret QB data; and (c) strengthen governance and accountability of SVP with suggested checks on potential risk areas.

## [GG-RATIONALE] Why agencies perform governance checks on QB data
page: 26

Why do we need to perform governance checks? QB enhances convenience for officers to purchase items from e-commerce malls and bill directly to their agencies, without additional paperwork or having to go through the buy-and-claim process. With that, it is good practice to leverage data to perform analytics on potential risk areas to uphold governance and guard against egregious activities. We note that there are limits to what can be identified or monitored, so these checks are complementary to the existing governance controls (e.g., cart limit, spend limit) built into QB's design to manage risk thresholds.

## [GG-CHECK-REASONS] Suggested governance check: anomalies in reasons for purchase
page: 20

Check: Anomalies in Reasons for Purchase indicated for QB transactions.

Purpose: To monitor for abuse of approval mechanism by ensuring accuracy in reasons for purchase provided.

Possible things to look out for:
- Vague reasons that do not explain the reason for the purchase (e.g., "QB buy", "QB transaction for approval pls").
- Search for keywords (e.g., "offline", "email", "refer") that could suggest duplicative approvals being sought offline.

How to obtain this data: (1) Download data from the Carts module and refer to the Carts file that is made available. (2) Open the file and filter by parameters (e.g., cost center code, time period) if required. (3) Do note to filter for 'approved' carts under the 'Cart_Status' column. (4) Under the 'Reason_For_Purchase' column, review the remarks provided for the purchases.

Possible follow up actions: Verify with buyers on reasons for purchase to ensure the transaction was bona fide and/or remind them to indicate clearer remarks for future QB purchases.

Please note that this list of suggested governance checks is non-exhaustive.

## [GG-CHECK-SPLIT] Suggested governance check: split purchases
page: 21

Check: Split purchases.

Purpose: To identify potential instances of split purchases to go under the SVP threshold radar and take advantage of the convenience of QB.

Possible things to look out for:
- Buyers with consecutive purchases of the same good / category of goods within a short period (e.g., 1 month) of time.
- Buyers in the same department with purchases of the same good / category of goods within a short period of time.

How to obtain this data: (1) Download data from the Invoices module. (2) [Invoices file] Ensure the desired period for the check is filtered for under the Order_Date column. (3) [Invoices file] Use the Buyer_Corporate_Email column to identify buyers with repeated purchases. (4) [Invoices and InvoiceItems files] Based on the data from step 3, cross reference (via vlookup/xlookup) the records between the files using the common data field (Invoice_ID column in the Invoices file and the Parent_Invoice_ID column in the InvoiceItems file). (5) [InvoiceItems file] Refer to data under the Product_Category column to analyse the category of goods purchased, or Item_Desc and Item_Desc_Details for details of purchases.

Possible follow up actions: Verify with the buyer on why the purchases were split. E.g., some e-commerce sellers limit the quantity of items per cart, and it could be the case where the buyer had to make multiple purchases to obtain the quantity they require.

Please note that this list of suggested governance checks is non-exhaustive.

## [GG-CHECK-INDISCRIMINATE] Suggested governance check: indiscriminate spending
page: 22

Check: Indiscriminate spending.

Purpose: To identify potential instances of indiscriminate spending and safeguard Government resources, i.e., ensure there was a requirement for purchase.

Possible things to look out for: Buyers with high frequency of buys at high amounts (e.g., just slightly under the agency cart limit) within a certain period (e.g., 1 month).

How to obtain this data: (1) Download data from the Invoices module. (2) [Invoices file] Ensure the desired period for the check is filtered for under the Order_Date column. (3) [Invoices file] Create a pivot table using data from the Buyer_Corporate_Email and Total_Amt_Payable columns to identify buyers with high frequency of buys at high amounts. For details of purchases, cross reference identified records between Invoices (Invoice_ID column) and InvoiceItems (Parent_Invoice_ID column), and refer to the Product_Category column or the Item_Desc / Item_Desc_Details columns in the InvoiceItems file.

Possible follow up actions: Check with buyers on reasons for their buying activity. Review if there needs to be clearer guidance or tighter controls within your agency for use of QB.

Please note that this list of suggested governance checks is non-exhaustive.

## [GG-CHECK-SPEND-PERIOD] Suggested governance check: spend per agency and per officer per 6-month period, and the central spend limit
page: 23

Check: Amount spent by agency and average amount spent by each officer per 6-month period.

Purpose: To analyse spend patterns and activity to guide decision-making.

Possible things to look out for:
- Amount spent by agency in a given period (e.g., 6 months).
- Average amount spent by each officer in each period (e.g., 6 months) and if there is a high percentage of it being just slightly below the agency cart limit.
- Comparison of spend amounts across different periods, e.g., first 6 months since go-live and subsequent 6 months.

How to obtain this data: (1) Download data from the Invoices module. (2) [Invoices file] Ensure the desired period for the check is filtered for under the Order_Date column. (3) [Invoices file] Create a pivot table using data from the Buyer_Corporate_Email and Total_Amt_Payable columns. (4) Obtain the respective amounts based on the pivot table (e.g., total spend amount for the agency, and dividing the total amount by the number of unique officers to obtain the average spend).

Possible follow up actions: Review if further action is required, e.g., to the agency cart limit, or understand from officers the reasons behind spikes/dips in spend activity. Provide recommendations to the QB team for the central spend limit.

Footnote: There is currently a centrally imposed spend limit of $6k per officer per 6-month period.

Please note that this list of suggested governance checks is non-exhaustive.

## [GG-CHECK-TOP-CATEGORY] Suggested governance check: top categories of goods purchased and their prices (price reasonableness, value for money)
page: 24

Check: Top category of goods purchased and their prices.

Purpose: To ensure value for money (VFM) by understanding spend patterns, assessing for price reasonableness and performing price benchmarking.

Possible things to look out for:
- Frequency of purchases within the top categories of goods.
- If spending is highest within the top categories.
- Fluctuations in the prices of the top categories of goods across different time periods.

How to obtain this data: (1) Download data from the Invoices module. (2) [InvoiceItems file] Ensure the desired period for the check is filtered for under the Invoice_Item_Created_On column. (3) [InvoiceItems file] Create a pivot table using the required data (e.g., Item_Desc, Item_Desc_Details, Product_Category, Unit_Price columns) to facilitate your analysis.

Possible follow up actions: Assess how the prices of items or average spend in top categories compare against other channels of SVP, e.g., buy-and-claims. Provide recommendations to the QB team if there are categories of goods not offered by e-commerce partners onboard QB but commonly purchased in other channels of SVP.

Please note that this list of suggested governance checks is non-exhaustive.

## [GG-CHECK-ADOPTION] Suggested governance check: officers with corporate billing accounts who made at least one QB purchase
page: 25

Check: Number of officers who have set up corporate billing accounts and made at least 1 QB purchase within the past X months (time period to be determined by agencies).

Purpose: To track the agency's adoption and utilisation rate of QB to guide decisions (e.g., comms efforts), and to understand reasons if the rate is assessed to be low.

Possible things to look out for: Percentage of officers with active corporate billing accounts but no transactions. Low or no increase in the number of corporate billing accounts set up across a period, e.g., first 6 months since go-live and subsequent 6 months.

How to obtain this data: Download data from the Corporate billing users & accounts module, filter by period (Request_Updated_On) and status (Corporate_Billing_Status), and count unique officers by Buyer_Corporate_Email. Download data from the Invoices module for the same period and cross reference Buyer_Corporate_Email to assess if each officer made at least 1 QB transaction.

Possible follow up actions: Check with buyers to understand why they are not using QB. Review if QB can be made available to more officers within your agency. Surface possible reasons discouraging adoption to the QB team.

Please note that this list of suggested governance checks is non-exhaustive.

## [GG-DATA-CARTS] Interpreting Carts data: carts, orders, order items, cart status and cancellation
page: 11-12

Three files (in csv format) are downloaded from the Carts module: Carts, Orders and OrderItems.

Carts file: Each transaction raised by a buyer is reflected as a cart. This file captures the cart level details (e.g., name and emails of the buyer and approver, reason for purchase and cart status).

Orders file: Each cart can have multiple orders. E.g., if a buyer's transaction (cart) has orders from 2 different sellers under the same e-commerce, each seller will have their own order. Order level details include the name of the seller, and discounts (if any) granted by the seller.

OrderItems file: Captures item-level details (e.g., item description, product category and unit price) of all items raised for purchase.

Key columns in the Carts file: Cart_Status reflects if the cart had been approved or rejected. Is_Cart_Cancelled: False = cart has not been cancelled by the buyer or e-commerce; True = cart has been cancelled by the buyer or e-commerce. Is_Delivery_Address_Changed: False = delivery address has not been changed by the buyer; True = delivery address has been changed by the buyer before the order was approved, or routed to e-commerce for fulfilment.

## [GG-DATA-ORDERS] Interpreting Orders and OrderItems columns: discounts, invoice and payment references, item cancellation
page: 13

Orders file: Additional_Discount reflects if any additional discount had been offered by the respective e-commerce (e.g., "0" means no additional discount, and "-3" means the e-commerce offered an additional discount of $3). Ref_Invoice_ID reflects whether the invoice was received and successfully reconciled against the approved cart; blank entries could mean that the invoice has been rejected or not received yet. Orders with total amounts of $0 will not have any invoices. Ref_Payment_ID: when an order has been successfully paid, a reference payment ID is generated and populated.

OrderItems file: Item_Status reflects if the item had been cancelled by either the buyer or the e-commerce. If it is empty, the item had not been cancelled. If "cancelled" is reflected, the item had been cancelled and the agency should not be invoiced for it.

## [GG-DATA-INVOICES] Interpreting Invoices and InvoiceItems data
page: 14-15

Two files (in csv format) are downloaded from the Invoices module: Invoices and InvoiceItems.

Invoices file: Details (e.g., buyer and seller names, order date) of invoices issued at order level. Reminder: each cart can have multiple orders, depending on the number of different sellers involved in the buyer's transaction from the e-commerce. FinSys_Payment_Voucher_Status and FinSys_Payment_Status columns let agencies monitor the payment status of their QB transactions; if blank, the payment voucher has yet to be created.

InvoiceItems file: Item level details (e.g., item description, product category and unit price) of each item within an invoice. The Item_Desc, Item_Desc_Details and Product_Category columns reflect the details of each item invoiced, for agencies to have clarity on the type/nature of goods purchased.

## [GG-DATA-ACCESS] Accessing QB data in the Admin Portal: filters, downloads and roles
page: 5-10, 26-27

Data is downloaded from the Carts, Invoices and Corporate billing users & accounts modules (filter, apply filters, download, then retrieve the csv file). By default, the overview page shows orders raised in the current month. When date filters (e.g., Order Date) have specific dates selected, both the data displayed on the overview page and the data available for download change; other filters only change the data displayed, not the data downloaded, as the intent is for agencies to have a complete dataset for analysis.

Admin Portal accounts are assigned by the agency's QB admins on the basis of need. Viewing and downloading Carts and Invoices data requires View and Download permissions for the Finance Operations section; Corporate billing data requires View and Download permissions for Corporate billing users & accounts.
