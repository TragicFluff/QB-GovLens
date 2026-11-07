# QB GovLens rule specification (tool documentation, not QB policy)

doc: RS
source_document: QB GovLens rule specification, written by the QB GovLens PoC team
curation_note: Describes how THIS prototype's screening rules work. It is not QB policy, not an official threshold, and not a finding standard. Where it relies on official guidance it names the Governance Guide (GG) or Data Glossary (DG) passage.

## [RS-SCOPE] What QB GovLens screens and how its outputs should be read
page: GovLens rule spec v1.3

QB GovLens produces review aids for agency administrators, not findings. Deterministic Python rules G2B and G2C decide which split-purchase patterns are flagged; a language model only explains a pattern after an admin selects it, citing retrieved passages. The purchase-justification check gives one tier per cart that combines the deterministic REASON check of the reason text, an AI assessment of the items against the stated reason, and a price comparison; the reasons for each tier are listed with it. It never changes the G2B or G2C tiers or counts. All outputs keep a non-accusatory tone: a pattern can have legitimate explanations, and the admin decides what it means and what happens next. The rules implement parts of the Governance Guide's suggested checks (split purchases, anomalies in reasons for purchase, top categories and prices); the guide notes its list of checks is non-exhaustive and complementary to QB's built-in controls.

## [RS-G2B] Rule G2B: one officer's spend spanning the six-monthly reset of the QB spend limit
page: GovLens rule spec v1.3

Basis: the Governance Guide states a centrally imposed spend limit of $6k per officer per 6-month period (GG-CHECK-SPEND-PERIOD) and suggests looking for buyers with consecutive purchases of the same good or category within a short period, e.g. 1 month (GG-CHECK-SPLIT). GovLens assumes the 6-month periods reset on 1 April and 1 October (Singapore financial-year halves); this reset timing is a tool assumption and is not stated in the Governance Guide.

Rule: for each agency and buyer (Buyer_Corporate_Email), take orders in the 30 days before and the 30 days after each 1 April / 1 October boundary, using Order_Date as the event date. A case is raised when there is spend on both sides and the combined Total_Amt_Payable exceeds $6,000. Priority increases with the amount above $6,000, with a product category shared across the boundary, and with meaningful words shared between the reasons for purchase; a pre/post order pair sharing BOTH a category and reason words is High. Repeat boundaries for the same officer add to the score. Welfare purchases (#welfare) and cancelled or non-approved carts are excluded.

Reading the result: spend across two separately refreshed limits is not by itself improper. Shared categories or reasons suggest, but do not prove, one continuing requirement. Legitimate explanations include genuinely separate needs and sellers limiting quantity per cart (GG-CHECK-SPLIT).

## [RS-G2C] Rule G2C: several buyers in the same cost centre buying the same product category in a half financial year
page: GovLens rule spec v1.3

Basis: the Governance Guide suggests looking for buyers in the same department with purchases of the same good or category of goods within a short period of time (GG-CHECK-SPLIT). GovLens uses the cost centre as the proxy for department.

Rule: group invoice items by agency, cost centre (item cost centre, falling back to the invoice cost centre), Product_Category and half financial year (Apr-Sep, Oct-Mar). Buyers contributing 10% or less of the group's spend are treated as non-material. A case is raised when at least two material buyers together spend more than the $6,000 screening amount. Priority increases when orders are close together in time, when different buyers' reasons share meaningful words, with the amount above $6,000, with more material buyers, and when the pattern recurs in more than one half-year. Same-day, same-seller orders with shared reasons from three or more material buyers are High. The $6,000 screening amount is a GovLens setting, not an official aggregate cost-centre limit.

Reading the result: colleagues in one cost centre can have independent, legitimate needs for the same category (e.g., pantry restocking by different teams). The pattern alone does not establish collusion or deliberate splitting.

## [RS-REASON] Reason check (REASON rule): vague reasons and possible offline approval references
page: GovLens rule spec v1.3

Basis: Governance Guide check on anomalies in reasons for purchase (GG-CHECK-REASONS), which asks reviewers to look for vague reasons (e.g. "QB buy", "QB transaction for approval pls") and keywords such as "offline", "email" or "refer" that could suggest duplicative approvals sought offline, among approved carts.

Rule (deliberately broad; more false alarms are accepted in this prototype): a reason is "vague" if it is blank, is only a QB/QuickBuy label with an optional year or generic word (e.g. "QB2025", "QB buy", "Quick buy 2025"), matches a list of generic phrases, or has fewer than two meaningful words and no purpose hashtag. A reason is a "possible offline approval reference" if it contains offline, email/e-mail, refer/referred, "as discussed", or approval wording such as approved/approval/pls approve. Both findings are passed to the AI assessment as pre-checks. Approval wording also sets a minimum purchase-justification level of Medium, so the AI cannot rate it away. A vague reason sets no minimum; the AI judges it under the purchase-justification prompt (a reason with no stated purpose is a documentation gap). Without an AI result, the tier is provisional: Medium for approval wording, Low for a vague reason. Only approved, non-cancelled carts are screened.

Reading the result: a keyword match is not proof that the approval process was bypassed; it may simply describe context (e.g. an email subscription). Follow up by verifying with the buyer and reminding officers to give clearer remarks (GG-CHECK-REASONS).

## [RS-AI-SCREEN] Purchase-justification check: one tier per cart (High, Medium or Low) from the reason check, an AI assessment and a price comparison
page: GovLens rule spec v1.3

Basis: the Governance Guide's purpose of ensuring there was a requirement for purchase (GG-CHECK-INDISCRIMINATE), accuracy of reasons for purchase (GG-CHECK-REASONS), and price reasonableness and benchmarking within product categories (GG-CHECK-TOP-CATEGORY).

Method: for each approved, non-cancelled, non-welfare cart, a language model receives the reason, the items, the REASON pre-checks and retrieved guidance passages. It assesses each item's core function against the stated Reason_For_Purchase and assigns a BASE tier: High (clear red flags that warrant investigation, including purchases that are indefensible), Medium (a plausible basis but notable gaps in the justification) or Low (broadly appropriate), or Uncertain; it ignores marketing themes but not luxury brand tier, and cites the guidance it relies on. It must not invent a purpose the reason does not state: when the reason gives no operational context (e.g. 'QB2025'), everyday low-cost items are Medium and specialised, costly or unusable items are High; agency purpose hashtags (e.g. #refillforpantry) count as a stated purpose. Python then computes each item's unit price after discount (Amount_After_Discount / Qty) and compares it with other carts' items in the same Product_Category across all agencies. If there are more than 5 comparison records and the item costs more than every one of them, it moves up one tier (capped at High); an item in the top 10% (between the 90th percentile and the maximum) is noted but keeps its tier, because product categories are broad. Price never lowers a tier. The cart takes its highest item tier, raised to Medium if the reason contains approval wording.

Reading the result: the tier is AI-assisted and is shown with the reasons that drove it (reason check, AI summary, price step). It is not used to raise or rank the G2B or G2C cases. Product categories are broad marketplace labels, so a price comparison can set an item against dissimilar goods in the same category; check the item description before acting.

## [RS-DATA] Data handling assumptions in QB GovLens
page: GovLens rule spec v1.3

Event date: Order_Date from the Invoices file is used as the event date for all time-window rules. Carts: only carts with Cart_Status = approved and Is_Cart_Cancelled = False are screened, following the guide's instruction to filter approved carts (GG-CHECK-REASONS). Welfare: carts or items flagged Welfare_Purchase = True (#welfare in the reason) are excluded from G2B, G2C and the AI screen. Amounts: invoice totals (Total_Amt_Payable) are counted once per invoice for G2B; item amounts (Amount_After_Discount) are used for G2C and price bands, and may not reconcile to invoice totals because of GST, shipping, discounts or rounding. Joins: invoices link to carts on Ref_Cart_ID = Cart_ID, and items link to invoices on Parent_Invoice_ID = Invoice_ID. Data in this prototype is masked or synthetic.
