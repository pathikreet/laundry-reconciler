# Features — Laundry Reconciler

The Laundry Reconciler is a comprehensive, local-first data integrity application built to automate the daily financial reconciliation of a laundry business. By ingesting disparate data sources (CRM, payment terminals, cash registers, and runner notepads), the system acts as a central truth engine, flagging discrepancies, missing funds, and policy violations.

## Core Capabilities

### 1. Unified Data Ingestion
The system normalizes and processes data from multiple independent formats:
- **CRM Sales & Orders:** Imports master operational data, updating new orders while treating legacy CRM data as immutable.
- **CRM Delivery:** Imports independent delivery event timestamps.
- **MSWIPE Payments:** Ingests batch POS terminal data (credit cards, GPay, UPI).
- **Cash Register:** Ingests the daily counter cash grid, deriving net counter balances.
- **Runner Notepad:** Digitizes the delivery runner's manual ledger (cash collected, online payments confirmed on doorstep).
- **Expenses (New):** Tracks business cash and online expenses to correctly offset derived cash register balances.

### 2. Intelligent Idempotent Importers
All data loaders use an idempotent, conflict-free strategy. 
- You can re-upload modified Excel sheets for a specific date, and the system uses a **delete-by-date** or **upsert** strategy. 
- It prevents duplicate entries without forcing you to manually clear databases or perform full wipes.
- Robust parsing normalizes Indian date formats (`DD-MM-YYYY`, `DD/MM/YYYY`) and cleans currency symbols instantly.
- Intelligent sub-string fallback maps messy handwritten notepad entries (e.g., `Cash-adv`, `paytm done`, `gpay to counter`) into standardized payment modes (`Cash`, `Paytm`, `GPay`).

### 3. Cross-Date Reconciliation Engine
At the heart of the system is the **ReconciliationService**, analyzing transactions across time to form a comprehensive ledger.
- Correlates payments made on Day 1 for an order delivered on Day 3 (advance payments).
- Correlates deliveries made on Day 1 for payments made on Day 4 (late payments).
- Correlates day-level cash surpluses on past dates with cash deficits on current dates (honest late-entry detection).

### 4. Granular Fraud Detection & Variance Exceptions
The rule engine applies strict business logic to generate specific, actionable exception alerts with associated severity levels.

#### Day-Level Variance Exceptions
- **`CashUndeposited` (🔴 High):** Identifies when CRM says cash was collected, but the cash register lacks a corresponding deposit. This explicitly detects pocketed cash, adjusting for legal counter expenses.
- **`CashVariance` (🔴 High):** Matches what the Runner Notepad says was collected against the net cash in the Register.
- **`GPayMismatch` (🔴 High / 🟡 Medium):** Total GPay marked in CRM is compared directly to MSWIPE daily settlement totals.

#### Order-Level Policy Exceptions
- **`CreditPolicyViolation` (🔴 High):** Flags when an order is handed over to the customer but the outstanding balance exceeds allowed credit limits.
- **`DeliveredNotMarkedCRM` / `DeliveredMissingNotepad` (🟡 Medium):** Flags logistical desyncs where CRM thinks an order is still processing, but the runner noted it as delivered (or vice versa).
- **`NotepadAmountMismatch` (🟡 Medium):** Flags discrepancies between the cash amount a runner claimed to collect vs. the authoritative CRM ledger.
- **`AgeingOrder` (🟡 Medium):** Flags orders sitting without delivery confirmation past their expected SLA.

#### Payment Discrepancy Exceptions
- **`BackdatedGPayPayment` (🕵️ Informational):** Detects delayed GPay entries in CRM that actually settle against MSWIPE batches from prior dates.
- **`SuspectedBackdatedCashPayment` (🕵️ Informational):** Explains a cash deficit today by finding an exact matching cash surplus in the register from a previous day.
- **`PaymentNotConfirmedByNotepad` (🔵 Low):** Notes when CRM marks a card/online payment, but the runner neglected to write it down.

### 5. Period Aggregation & Netting
- **Period Summary Views:** Flattens daily noise over a month or quarter. If the register was short ₹500 on Monday, but over by ₹500 on Tuesday, the Period Summary nets this to zero and marks the exceptions as "Self-Correcting".
- This isolates **Persistent Exceptions**—showing only the genuine, unresolved discrepancies that actually represent lost revenue.

### 6. Interactive User Interface
- **Streamlit Wizard Dashboard:** A beautiful 7-step guided pipeline for data imports.
- **Visual Status Tracking:** Color-coded badges and progress bars indicating import status.
- **Interactive Drill-downs:** Click to expand specific exception rules to view exactly which orders or dates contributed to a variance.
- **Exception Context:** UI tooltips explain exactly *why* a rule was broken and suggest an investigative action.

### 7. Export & Reporting
- **Multi-Sheet Excel Audits:** Generates a comprehensive Excel export containing Orders, Exceptions, Notepad logs, MSWIPE logs, a Summary sheet, and a full system Audit trail.
