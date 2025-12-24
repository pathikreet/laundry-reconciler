# PRD — Laundry Reconciler (MVP)

## 1) Overview

### 1.1 Product goal
Build an MVP app called Laundry Reconciler that reduces daily reconciliation time by importing exports from CRM, MSWIPE, and the cash register Excel, plus runner notepad entries, then auto-matching orders and payments and flagging exceptions for quick closure.

### 1.2 Users
- Store owner/manager: imports files, reviews mismatches, finalizes day close, exports results.
- (Future) Runner: direct entry of delivery/payment events (out of MVP unless explicitly added).

### 1.3 Primary problems to solve
- Deliveries sometimes recorded only in CRM, only in notepad, or in both.
- Cash and Google Pay entries are manually marked (error-prone) and need systematic validation.
- Orders can have advance/partial payments before delivery; on delivery day the CRM payment field may be 0 even though the order is fully paid.
- Business policy discourages credit; any delivered order with remaining balance should be flagged.

### 1.4 Success criteria
- Reduce reconciliation effort to < 15 minutes/day.
- Auto-match ≥ 90% of daily activity (order-level and payment-level) with a clear “why” for every exception.
- Export an Excel workbook that can be used as a “fix list” for CRM corrections.

---

## 2) Inputs & normalization

### 2.1 CRM sales export (Excel/CSV)
#### Required fields (provide a column-mapping UI because headers vary)
- Order Number (string, ideally unique)
- Order Date (date)
- Customer Name (string)
- Delivery Date (date; may be blank)
- Payment Date (date; may be blank)
- Order Amount (number)
- Payment Amount (number; may be 0/blank)
 - Payment Mode (Cash / Google Pay / Paytm / Package / Other)
- Marked By (Runner / Manager)

#### Normalization rules
- Trim whitespace, normalize casing for names.
- Parse dates robustly (multiple formats).
- Parse numeric amounts; handle commas and currency symbols.
- Standardize payment modes via a mapping table (user-editable).

- `Online TransactionID` and `Payment Mode` mapping:
  - Use `Online TransactionID` (when present) to identify and link `Paytm` payments from the CRM export to corresponding provider transactions.
  - The CRM `Payment Mode` value `Paytm` (or variants) should map to the `Paytm` mode in the app.

- Interpret `Adjustments`:
  - The CRM `Adjustments` field denotes returns or payment reversals for that order. If `Adjustments` is non-zero, treat it as an order return/backout and reconcile `Payment Received` and `Balance` accordingly (i.e., a positive Adjustment typically reduces `Payment Received` or increases `Balance`).

### 2.2 Runner notepad (manual entry + optional OCR)
#### MVP ingestion
- Manual entry screen (fast grid entry) for notepad lines.

#### Optional feature (behind a toggle)
- OCR a notepad screenshot to prefill rows; user must review and confirm.

#### Notepad line fields
- Order Number (optional)
- Customer Name (optional)
- Amount Collected (number)
- Payment Mode (Cash / Google Pay / etc.)
- Delivery date/time (optional)
- Runner name/id (optional)
- Notes (optional)

### 2.3 MSWIPE daily payments export (Excel/CSV)
#### Required fields (with mapping UI)
- Transaction DateTime
- Amount
- Status (filter to Successful)
- Payment instrument/mode (identify Google Pay / UPI bucket)
- Reference/Txn ID (if present)

#### Normalization rules
- Include only successful transactions.
- Bucket transactions into the business day using local timezone.
- Store raw + normalized forms for auditability.

#### Practical mapping heuristics (MSWIPE sample guidance)
- Some MSWIPE/aggregator exports do not include an explicit `Status` column named "Status". If no explicit status exists, treat rows as "Successful" when `FinalPayment`, `NetAmt`, or `TxnAmt` > 0, unless a provider-specific remarks/status field maps to failure values.
- Common header variants to autosuggest in the mapping UI: `TxnDate` / `TransactionDate` / `Transaction Date`, `PaymentDate`, `TxnAmt` / `Amount` / `NetAmt` / `FinalPayment`, `RR_NO` / `Stan_No` / `Mswipe_Ref_No` / `ARN` for reference IDs.
- Payment-mode normalization: prefer `Interchange`, `CardType`, or `PayeeVPA` to identify UPI/Google Pay; map `UPI`, `GPay`, `Google Pay`, `BHIM`, and empty VPA patterns appropriately.
- App classification rule: any payment present in the MSWIPE transactions will be classified and shown as `GPay` (Google Pay/UPI) inside the Laundry Reconciler app for day-totals and GPay-specific checks, regardless of the original label in the MSWIPE export; preserve the original provider label/value in the normalized record for audit and manual review.
- Day-bucketing precedence: use `PaymentDate` for assigning the business day when present; fall back to `TxnDate` otherwise.
- Amount choice for reconciliation: prefer `FinalPayment` or `NetAmt` (post-fees) for day-level totals and linking to CRM amounts; fall back to `TxnAmt` if `NetAmt`/`FinalPayment` are missing.
- If multiple potential identifier columns exist (e.g., `RR_NO`, `Stan_No`, `Mswipe_Ref_No`, `ARN`), store them all in the normalized record and use them for best-effort linking and audit.
- Mapping UI should allow users to mark which column indicates success/failure when provider-specific labels are used (e.g., `REMARKS`, `PaymentRemarks1`).

### 2.4 Daily cash register Excel (calendar grid layout)
The cash register is an Excel workbook where each year is a sheet, months are columns, days-of-month are rows, and each day’s cell contains the accumulated closing cash balance (already net of cash expenses and bank deposits). [web:17]

#### Requirements
- UI to select the year sheet and map:
  - Which columns correspond to months.
  - Which rows correspond to day-of-month.
 - For a selected date `d`, read:
  - `C_d`: closing cash for date `d`
  - `C_(d-1)`: closing cash for previous day (if available)
- Allow optional manual input `E_d`: total cash expenses + cash bank deposits for day `d` (if not stored elsewhere).
 - If `C_(d-1)` is missing, recursively check for previous days (e.g `C_(d-2)`, `C_(d-3)`, etc.) till 5 days (`C_(d-5)`), as there can be a holiday at those days.
  - When `d` is the first day of a month, `C_(d-1)` may be recorded in the previous month's column; the mapping UI and lookup logic must handle cross-month lookups (previous column) within the same year sheet and across month boundaries.
- If data is missing till `C_(d-5)`, prompt for manual prior closing, or mark cash validation as “partial”.

#### Derived signal
Approximate cash-from-orders signal:
- `CashFromOrders_d ≈ C_d - C_(d-1) + E_d`

---

## 3) Reconciliation model & rules

### 3.1 Core concepts (events vs orders)
Treat “delivery” and “payment” as separate event streams that can occur on different dates:
- Deliveries are grouped by Delivery Date (Notepad data is the source of truth).
- Payments are grouped by Payment Date (MSWIPE is payment-day truth for Google Pay/UPI).

A reconciliation run for date `D` must support two views:
- Delivery Day Close (D): delivery-focused exceptions and cash collection checks.
- Payment Day Close (D): payment-focused exceptions including advances for undelivered orders.

### 3.2 Tolerances (defaults + configurable)
Add settings that can be changed globally and per reconciliation run:
- AmountMatchToleranceINR: ₹2
- DailyTotalToleranceINR: ₹10
- DailyTotalTolerancePercent: 0.5%
- MSWIPETimeMatchWindowMinutes: 180
- FuzzyNameMinScore: 0.82 (implementation-defined)
- FuzzyDateProximityDays: 3
- CashVarianceToleranceINR: ₹100
- CashVarianceTolerancePercent: 1.0%

Rules:
- Order-level matching uses AmountMatchToleranceINR.
- Day-level comparisons use the larger of DailyTotalToleranceINR or DailyTotalTolerancePercent.

### 3.3 Storage model (must persist history)
Because advances and partial payments can occur days before delivery, the system must persist order history across dates (not just single-day processing), including imports, normalization, matches, and manual overrides. [web:19]

Create internal entities:
- `Order` (from CRM)
- `PaymentEvent` (from CRM payment rows and from MSWIPE transactions)
- `DeliveryEvent` (from notepad and CRM delivery fields)
- `ReconciliationRun` (date-scoped processing snapshot, results, and audit log)

### 3.4 Matching strategy (priority order)
1. Exact match by Order Number (CRM ↔ Notepad).
2. If Order Number missing:
   - Fuzzy match by customer name similarity, amount tolerance, and date proximity.
   - Use runner/marked-by hints when available.
3. Every match must have:
   - Confidence score
   - Explanation (which fields matched, what tolerance applied)
4. Below a confidence threshold, require manual review.

### 3.5 Advance and partial payments (order mini-ledger)
For each order, compute:
- `OrderAmount`
- `TotalPaidToDate` (sum of linked successful payments)
- `AdvancePaidBeforeDelivery` (sum where PaymentDate < DeliveryDate)
- `PaidOnDeliveryDay` (sum where PaymentDate = DeliveryDate)
- `BalanceDueAtDelivery = OrderAmount − TotalPaidToDate`

Rules:
- If delivered on date `D` and CRM payment amount on `D` is 0:
  - Do not flag as unpaid if `TotalPaidToDate ≥ OrderAmount`.
- For partial advances:
  - Expect remaining balance to be collected on delivery day (cash or GPay/UPI), unless explicitly marked as exception.

### 3.6 Delivery status rules
- If notepad shows delivered but CRM Delivery Date is blank → flag “Delivered not marked in CRM” (High).
- If CRM Delivery Date exists but notepad has no entry → flag “Delivered missing in notepad” (Medium/Low).

### 3.7 Payment rules

#### 3.7.1 Order-level checks (CRM vs Notepad)
Per order:
- Amount mismatch → High.
- Mode mismatch but amount matches → Medium.
- Duplicate notepad entries for the same order number → Medium/High.

#### 3.7.2 Google Pay validation (CRM vs MSWIPE)
Day-level totals:
- `TotalGPay_CRM`: sum of CRM payments marked as Google Pay for date `D` (by Payment Date; fallback to Delivery Date only when Payment Date is missing and payment amount > 0).
- `TotalGPay_MSWIPE`: sum of MSWIPE successful Google Pay/UPI for date `D`.

Rules:
- If `TotalGPay_MSWIPE > TotalGPay_CRM` beyond tolerance:
  - Flag “Missing or misclassified GPay entries in CRM”.
- If `TotalGPay_CRM > TotalGPay_MSWIPE` beyond tolerance:
  - Flag “Possible paid-but-not-received, wrong mode, or duplicate in CRM”.
  - Identify candidate problematic orders:
    - Orders with CRM payment mode = Google Pay
    - No matching MSWIPE transaction within amount tolerance + time window
  - Rank candidates by likelihood and show an actionable list:
    - “Marked as GPay in CRM but no matching MSWIPE payment found”

MSWIPE-to-order linking:
- Attempt best-effort match by amount and time window.
- If MSWIPE export lacks order/customer identifiers, treat it as a strong day-total truth and keep linking as “probabilistic”.

#### 3.7.3 Cash validation (orders vs cash register)
- Compute expected cash received from reconciled orders marked Cash:
  - Prefer notepad for “collected on delivery” when CRM is missing, but keep a confidence flag.
- Derive cash-from-orders signal from cash register closing balances:
  - `CashFromOrders_d ≈ C_d - C_(d-1) + E_d`
- Compare expected cash vs derived cash signal; if variance exceeds tolerance, flag “Cash variance”.

### 3.8 No-credit policy enforcement
Flag “Credit Policy Violation” (High) when:
- Order is delivered (Delivery Date exists), and
- `BalanceDueAtDelivery > CreditToleranceINR` (default ₹1), and
- There is no notepad entry and no payment event on (or immediately around) delivery day that settles the remaining balance.

### 3.9 Severity and explainability
Every exception must include:
- Severity: High / Medium / Low
- Reason tags (multiple)
- Evidence (source fields and values)
- Suggested action (e.g., “Check if payment received”, “Correct mode in CRM”, “Mark delivered in CRM”, “Resolve duplicate”)

---

## 4) UX & outputs

### 4.1 Required screens
- Import Wizard
  - Select date (or date range)
  - Upload CRM + map columns (save mapping profile)
  - Upload MSWIPE + map columns
  - Upload Cash Register + select year sheet + map months/days + preview chosen date’s `C_d` cell
  - Enter notepad lines (grid) and/or upload screenshot (OCR optional)
- Results
  - Reconciled Orders table (filter/sort by severity, payment mode, runner, marked-by)
  - Exceptions queue with “Resolve” actions:
    - Link notepad entry to order
    - Mark as false positive
    - Add manual note
  - Daily Summary
    - Totals by payment mode (CRM vs Notepad vs MSWIPE)
    - Cash variance signal vs expected cash

### 4.2 Exports (Excel workbook)
Export a workbook with sheets:
- Reconciled_Orders
- Exceptions
- Unmatched_Notepad
- Unmatched_MSWIPE
- Daily_Summary
- Audit_Log

Each exception row must contain a “reason” column with clear text explanations suitable for daily ops.

---

## 5) Tech, data store, non-functional requirements, acceptance

### 5.1 Implementation language & local data store
Implement the MVP in Python. Use a local embedded datastore for persistence of runs, records, overrides, and audit logs (no external server required).

Example acceptable options (Python-friendly):
- **SQLite (recommended):** reliable, ACID, widely available; use with `SQLAlchemy` and JSON columns for event/document storage when needed.
- **TinyDB:** pure-Python document store (JSON-backed) for a lightweight, schema-flexible option suited to small deployments.
- **LMDB / RocksDB bindings:** for higher-performance local key-value needs (only if profiling shows need).

Suggested Python libraries for MVP:
- `pandas`, `openpyxl`, `xlrd` — Excel/CSV parsing and preview
- `python-dateutil` — robust date parsing
- `rapidfuzz` or `thefuzz` — fuzzy name matching
- `pytesseract` (optional) — OCR for notepad screenshots
- `xlsxwriter` or `openpyxl` — export Excel workbook

### 5.2 Non-functional requirements
- Performance: handle at least 500 orders/day and finish reconciliation within 30 seconds on a typical laptop.
- Reliability: clear error messages for missing columns, unreadable Excel sheets, invalid dates, and unmapped payment modes.
- Auditability: log every import, match decision, and manual override.

### 5.3 Acceptance criteria (MVP must pass)
- User can import all four inputs, map columns, and run reconciliation for a selected date.
- App generates:
  - Reconciled table with per-order status
  - Exceptions list with reasons and suggested actions
  - Flags for “Delivered not marked in CRM”
  - Flags for “Possible payment not received” when CRM GPay totals exceed MSWIPE and specific orders have no matching MSWIPE txn
  - Cash variance comparison using the closing-balance grid layout. [web:17]
- App exports the required Excel workbook with the defined sheets.
