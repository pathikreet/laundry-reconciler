# TASKS.md — Laundry Reconciler MVP

## Task Overview

This document breaks down the Laundry Reconciler PRD into actionable development tasks. The approach follows:

1. **Foundation First**: Data layer and core infrastructure
2. **Input Processing**: File import, parsing, and normalization
3. **Core Logic**: Matching engine and reconciliation rules
4. **User Interface**: Import wizard and results screens
5. **Output Generation**: Excel export and reporting
6. **Polish**: Configuration, error handling, and optimization

---

## Task Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              MILESTONE 1: Foundation                             │
│  ┌─────────────┐                                                                │
│  │  DATA-001   │ Database Schema & Setup                                        │
│  └──────┬──────┘                                                                │
│         │                                                                       │
│         ▼                                                                       │
│  ┌─────────────┐                                                                │
│  │  DATA-002   │ Data Access Layer (Repository Pattern)                        │
│  └──────┬──────┘                                                                │
│         │                                                                       │
│         ▼                                                                       │
│  ┌─────────────┐                                                                │
│  │  CFG-001    │ Configuration & Tolerance Settings                            │
│  └─────────────┘                                                                │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           MILESTONE 2: Import Pipeline                          │
│                                                                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐         │
│  │  IMP-001    │   │  IMP-002    │   │  IMP-003    │   │  IMP-004    │         │
│  │ CRM Import  │   │ MSWIPE Imp  │   │ Cash Reg    │   │ Notepad     │         │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘         │
│         └──────────────────┴─────────────────┴────────────────┘                │
│                                     │                                           │
│                                     ▼                                           │
│                            ┌─────────────┐                                      │
│                            │  IMP-005    │                                      │
│                            │Column Mapper│                                      │
│                            └─────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          MILESTONE 3: Matching Engine                           │
│                                                                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                           │
│  │  MATCH-001  │──▶│  MATCH-002  │──▶│  MATCH-003  │                           │
│  │ Exact Match │   │ Fuzzy Match │   │ Confidence  │                           │
│  └─────────────┘   └─────────────┘   └─────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         MILESTONE 4: Reconciliation Rules                       │
│                                                                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐         │
│  │  RECON-001  │   │  RECON-002  │   │  RECON-003  │   │  RECON-004  │         │
│  │Order Ledger │──▶│Delivery Rul │──▶│Payment Rules│──▶│Credit Policy│         │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘         │
│                                                              │                  │
│                                     ┌────────────────────────┘                  │
│                                     ▼                                           │
│                            ┌─────────────┐   ┌─────────────┐                    │
│                            │  RECON-005  │──▶│  RECON-006  │                    │
│                            │ GPay Valid  │   │ Cash Valid  │                    │
│                            └─────────────┘   └─────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              MILESTONE 5: User Interface                        │
│                                                                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐         │
│  │   UI-001    │──▶│   UI-002    │──▶│   UI-003    │──▶│   UI-004    │         │
│  │Import Wizard│   │Results Table│   │ Exceptions  │   │Daily Summary│         │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            MILESTONE 6: Export & Polish                         │
│                                                                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐         │
│  │   EXP-001   │   │   NFR-001   │   │   NFR-002   │   │   OPT-001   │         │
│  │ Excel Export│   │Error Handlng│   │   Logging   │   │ OCR Feature │         │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              MILESTONE 7: Testing                               │
│                                                                                 │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐         │
│  │  TEST-001   │   │  TEST-002   │   │  TEST-003   │   │  TEST-004   │         │
│  │Data Layer UT│   │ Import UT   │   │ Matching UT │   │ Recon UT    │         │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘         │
│         └──────────────────┴─────────────────┴────────────────┘                │
│                                     │                                           │
│                                     ▼                                           │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                           │
│  │  TEST-005   │──▶│  TEST-006   │──▶│  TEST-007   │                           │
│  │ E2E Integ   │   │ UI Integ    │   │ Error/Audit │                           │
│  └─────────────┘   └─────────────┘   └─────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Milestone Mapping

| Milestone | Tasks | Description | Target Duration |
|-----------|-------|-------------|-----------------|
| **M1: Foundation** | DATA-001, DATA-002, CFG-001 | Database, DAL, configuration | 2-3 days |
| **M2: Import Pipeline** | IMP-001 to IMP-005 | All file import and normalization | 4-5 days |
| **M3: Matching Engine** | MATCH-001 to MATCH-003 | Order matching with confidence | 3-4 days |
| **M4: Reconciliation** | RECON-001 to RECON-006 | Business rules and validation | 4-5 days |
| **M5: User Interface** | UI-001 to UI-004 | All screens per PRD §4.1 | 4-5 days |
| **M6: Export & Polish** | EXP-001, NFR-001, NFR-002, OPT-001 | Export, error handling, optional features | 3-4 days |
| **M7: Testing** | TEST-001 to TEST-007 | Unit tests and integration tests | 5-6 days |

---

## Task List

---

### MILESTONE 1: Foundation

---

## Task ID: DATA-001
### Title: Database Schema Design & SQLite Setup

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: None

#### Description
Design and implement the SQLite database schema for all core entities. The schema must support cross-date reconciliation history, audit logging, and flexible JSON storage for variable fields. Per PRD §3.3 and §5.1.

#### Acceptance Criteria
- [ ] SQLite database file is created with proper initialization
- [ ] `orders` table stores all CRM order data with normalized fields
- [ ] `payment_events` table stores both CRM payments and MSWIPE transactions
- [ ] `delivery_events` table stores notepad and CRM delivery entries
- [ ] `reconciliation_runs` table stores date-scoped processing snapshots
- [ ] JSON columns are used for flexible/audit fields
- [ ] Proper indexes on frequently queried columns (order_number, dates, etc.)
- [ ] Database migrations/versioning strategy implemented

#### Technical Notes
- Use SQLAlchemy for ORM and migrations
- Store raw + normalized forms for auditability (PRD §2.3)
- Include `created_at`, `updated_at` timestamps on all tables
- Support for `Online TransactionID` linking (PRD §2.1)
- Handle `Adjustments` field as returns/reversals (PRD §2.1)

#### Sample Data Reference
- Use `SalesAndDeliveryCRMExport-November.xlsx` to validate Order schema
- Use `Mswipe-Transactions-November.csv` to validate PaymentEvent schema

---

## Task ID: DATA-002
### Title: Data Access Layer (Repository Pattern)

**Priority**: P0  
**Estimated Effort**: 5 hours  
**Dependencies**: DATA-001

#### Description
Implement a repository pattern for all database operations, providing clean interfaces for CRUD operations and complex queries needed by the reconciliation engine.

#### Acceptance Criteria
- [ ] `OrderRepository` with methods: create, get_by_id, get_by_order_number, get_by_date_range, update
- [ ] `PaymentEventRepository` with methods for linking to orders and date-based queries
- [ ] `DeliveryEventRepository` with source-tracking (notepad vs CRM)
- [ ] `ReconciliationRunRepository` for snapshots and audit queries
- [ ] All repositories handle JSON serialization/deserialization
- [ ] Unit tests for all repository methods

#### Technical Notes
- Use context managers for transactions
- Implement bulk insert for performance (500+ orders/day requirement, PRD §5.2)
- Return domain objects, not raw database rows

#### Sample Data Reference
N/A - Test with mock data and schema from DATA-001

---

## Task ID: CFG-001
### Title: Configuration & Tolerance Settings Management

**Priority**: P0  
**Estimated Effort**: 4 hours  
**Dependencies**: DATA-001

#### Description
Implement a configuration system for all tolerances and settings defined in PRD §3.2. Settings should have global defaults and be overridable per reconciliation run.

#### Acceptance Criteria
- [ ] Configuration dataclass/model with all tolerances from PRD §3.2:
  - `AmountMatchToleranceINR`: ₹2
  - `DailyTotalToleranceINR`: ₹10
  - `DailyTotalTolerancePercent`: 0.5%
  - `MSWIPETimeMatchWindowMinutes`: 180
  - `FuzzyNameMinScore`: 0.82
  - `FuzzyDateProximityDays`: 3
  - `CashVarianceToleranceINR`: ₹100
  - `CashVarianceTolerancePercent`: 1.0%
  - `CreditToleranceINR`: ₹1 (per PRD §3.8)
- [ ] Global settings stored in database or config file
- [ ] Per-run override capability
- [ ] Payment mode mapping table (user-editable per PRD §2.1)
- [ ] Settings validation with sensible min/max bounds

#### Technical Notes
- Consider using Pydantic for validation
- Payment mode mapping: normalize "GPay", "Google Pay", "UPI", "BHIM" → standard mode
- Day-level comparisons use max(absolute, percentage) tolerance (PRD §3.2)

#### Sample Data Reference
N/A

---

### MILESTONE 2: Import Pipeline

---

## Task ID: IMP-001
### Title: CRM Sales Export Parser

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: DATA-002, CFG-001

#### Description
Implement the CRM Excel/CSV import pipeline with column mapping, normalization, and persistence. Must handle all fields listed in PRD §2.1.

#### Acceptance Criteria
- [ ] Parse Excel (.xlsx, .xls) and CSV files
- [ ] Support dynamic column mapping via configuration
- [ ] Normalize all fields per PRD §2.1:
  - Trim whitespace, normalize casing for names
  - Parse dates robustly (multiple formats)
  - Parse numeric amounts (handle commas, currency symbols)
  - Standardize payment modes via mapping table
- [ ] Handle `Online TransactionID` for Paytm linking
- [ ] Interpret `Adjustments` as returns/reversals
- [ ] Validate required fields and report clear errors
- [ ] Persist raw + normalized data to database
- [ ] Support incremental imports (don't duplicate existing orders)

#### Technical Notes
- Use pandas + openpyxl for parsing
- Use python-dateutil for robust date parsing
- Store original values in JSON column for audit
- Handle empty/blank Payment Date (PRD §2.1)

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx` for testing

---

## Task ID: IMP-002
### Title: MSWIPE Transactions Parser

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: DATA-002, CFG-001

#### Description
Implement the MSWIPE Excel/CSV import pipeline with filtering, normalization, and day-bucketing. Must follow all mapping heuristics from PRD §2.3.

#### Acceptance Criteria
- [ ] Parse Excel and CSV formats
- [ ] Support dynamic column mapping with auto-suggestions (PRD §2.3):
  - Date columns: `TxnDate`, `TransactionDate`, `PaymentDate`
  - Amount columns: `TxnAmt`, `Amount`, `NetAmt`, `FinalPayment`
  - Reference columns: `RR_NO`, `Stan_No`, `Mswipe_Ref_No`, `ARN`
- [ ] Filter to successful transactions only (heuristics per PRD §2.3)
- [ ] Identify Google Pay/UPI via `Interchange`, `CardType`, `PayeeVPA`
- [ ] Classify all MSWIPE payments as `GPay` in app (preserve original label)
- [ ] Day-bucketing: use `PaymentDate`, fallback to `TxnDate`
- [ ] Amount preference: `FinalPayment` > `NetAmt` > `TxnAmt`
- [ ] Store all identifier columns for best-effort linking

#### Technical Notes
- Handle absent Status column (treat rows as Successful if amount > 0)
- Bucket transactions to business day using local timezone (PRD §2.3)
- Store raw + normalized forms

#### Sample Data Reference
- `Mswipe-Transactions-November.csv` for testing

---

## Task ID: IMP-003
### Title: Cash Register Parser (Calendar Grid Layout)

**Priority**: P0  
**Estimated Effort**: 8 hours  
**Dependencies**: DATA-002, CFG-001

#### Description
Implement the cash register Excel parser that handles the unique calendar grid layout (years as sheets, months as columns, days as rows). Must handle cross-month lookups.

#### Acceptance Criteria
- [ ] UI/API to select year sheet
- [ ] Map month columns and day-of-month rows
- [ ] For a given date `d`, extract:
  - `C_d`: closing cash for date `d`
  - `C_(d-1)`: closing cash for previous day
- [ ] Handle cross-month lookups (first day of month → previous column)
- [ ] Recursive lookback up to 5 days if data missing (holidays)
- [ ] Support manual input for `E_d` (expenses + bank deposits)
- [ ] Compute derived signal: `CashFromOrders_d ≈ C_d - C_(d-1) + E_d`
- [ ] Mark validation as "partial" if data missing beyond 5 days

#### Technical Notes
- Complex Excel parsing: may need manual cell address calculation
- Handle merged cells if present
- Validate extracted values are numeric

#### Sample Data Reference
- `DailyCashRegister.xlsx` for testing

---

## Task ID: IMP-004
### Title: Runner Notepad Entry System

**Priority**: P0  
**Estimated Effort**: 5 hours  
**Dependencies**: DATA-002

#### Description
Implement the manual entry system for runner notepad lines with fast grid entry. Per PRD §2.2.

#### Acceptance Criteria
- [ ] Grid entry interface for notepad lines
- [ ] Support all notepad fields:
  - Order Number (optional)
  - Customer Name (optional)
  - Amount Collected (required)
  - Payment Mode (required)
  - Delivery date/time (optional)
  - Runner name/id (optional)
  - Notes (optional)
- [ ] Quick keyboard navigation for fast entry
- [ ] Validation of required fields
- [ ] Persistence to database
- [ ] Edit/delete existing entries

#### Technical Notes
- Optimize for speed (main use case is quick data entry)
- Consider copy-paste from spreadsheet
- Store raw values for audit

#### Sample Data Reference
N/A - Manual entry

---

## Task ID: IMP-005
### Title: Column Mapping Engine with Profile Persistence

**Priority**: P1  
**Estimated Effort**: 5 hours  
**Dependencies**: IMP-001, IMP-002, IMP-003

#### Description
Create a reusable column mapping engine that allows users to map source columns to expected fields, with auto-detection and profile saving. Per PRD §2.1, §2.3.

#### Acceptance Criteria
- [ ] Generic mapping UI component for any import type
- [ ] Auto-detect common column name patterns
- [ ] Display sample values to aid mapping decisions
- [ ] Validate all required columns are mapped
- [ ] Save mapping profiles to database
- [ ] Load and apply saved profiles
- [ ] Support multiple profiles per import type
- [ ] Mark failure value mappings for Status fields (PRD §2.3)

#### Technical Notes
- Reuse across CRM, MSWIPE, and Cash Register imports
- Consider fuzzy column name matching for auto-detection
- Store profiles in JSON format

#### Sample Data Reference
- All sample files for testing auto-detection

---

### MILESTONE 3: Matching Engine

---

## Task ID: MATCH-001
### Title: Exact Order Matching (Order Number)

**Priority**: P0  
**Estimated Effort**: 4 hours  
**Dependencies**: DATA-002, IMP-001, IMP-004

#### Description
Implement exact matching of CRM orders to notepad entries by Order Number. This is the highest priority matching strategy per PRD §3.4.

#### Acceptance Criteria
- [ ] Match CRM orders to notepad entries by exact Order Number
- [ ] Handle case variations (normalize before matching)
- [ ] Handle whitespace/formatting differences
- [ ] Record match with 100% confidence
- [ ] Generate explanation: "Matched by exact order number"
- [ ] Flag duplicate matches (same order number in multiple notepad entries)

#### Technical Notes
- Normalize order numbers: strip whitespace, uppercase
- Handle common variations (leading zeros, etc.)
- This runs before fuzzy matching

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx` for order numbers

---

## Task ID: MATCH-002
### Title: Fuzzy Order Matching (Name + Amount + Date)

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: MATCH-001, CFG-001

#### Description
Implement fuzzy matching for orders/notepad entries without order numbers, using customer name similarity, amount tolerance, and date proximity. Per PRD §3.4.

#### Acceptance Criteria
- [ ] Fuzzy match by customer name using `rapidfuzz`
- [ ] Apply `FuzzyNameMinScore` threshold (0.82 default)
- [ ] Apply `AmountMatchToleranceINR` (₹2 default)
- [ ] Apply `FuzzyDateProximityDays` (3 days default)
- [ ] Use runner/marked-by hints when available
- [ ] Combine factors into weighted confidence score
- [ ] Generate explanation showing which fields matched and tolerances applied
- [ ] Flag potential duplicates for manual review

#### Technical Notes
- Handle Hindi/English name variations
- Consider phonetic matching for names
- Weight factors: exact amount > close amount, exact date > proximity

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx` for customer names

---

## Task ID: MATCH-003
### Title: Confidence Scoring & Manual Review Queue

**Priority**: P0  
**Estimated Effort**: 5 hours  
**Dependencies**: MATCH-001, MATCH-002

#### Description
Implement a confidence scoring framework that assigns scores to all matches and routes low-confidence matches to a manual review queue. Per PRD §3.4.

#### Acceptance Criteria
- [ ] Confidence score calculation (0-100%) for all matches
- [ ] Score factors include:
  - Match type (exact vs fuzzy)
  - Name similarity score
  - Amount match precision
  - Date proximity
  - Runner/marked-by agreement
- [ ] Configurable threshold for automatic vs manual review
- [ ] Manual review queue with match candidates
- [ ] User can confirm, reject, or override matches
- [ ] All decisions logged for audit

#### Technical Notes
- Store match metadata (factors, scores) for explanation
- Consider showing top 3 candidate matches for manual review
- Integrate with exception system

#### Sample Data Reference
N/A

---

### MILESTONE 4: Reconciliation Rules

---

## Task ID: RECON-001
### Title: Order Mini-Ledger (Advance & Partial Payments)

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: MATCH-003, DATA-002

#### Description
Implement the per-order mini-ledger that tracks payments across dates, handling advances and partial payments. Per PRD §3.5.

#### Acceptance Criteria
- [ ] For each order, compute:
  - `OrderAmount`
  - `TotalPaidToDate` (sum of linked successful payments)
  - `AdvancePaidBeforeDelivery` (payments where PaymentDate < DeliveryDate)
  - `PaidOnDeliveryDay` (payments where PaymentDate = DeliveryDate)
  - `BalanceDueAtDelivery = OrderAmount − TotalPaidToDate`
- [ ] Link multiple payment events to single order
- [ ] Handle payments spanning multiple days
- [ ] Do not flag as unpaid if `TotalPaidToDate ≥ OrderAmount` (even if CRM shows 0)
- [ ] Store ledger state with each reconciliation run

#### Technical Notes
- Cross-date queries are essential (PRD §3.3)
- Handle partial payment scenarios
- Update ledger incrementally as new payments arrive

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx` for payment patterns

---

## Task ID: RECON-002
### Title: Delivery Status Rules Engine

**Priority**: P0  
**Estimated Effort**: 4 hours  
**Dependencies**: RECON-001, IMP-001, IMP-004

#### Description
Implement delivery status reconciliation rules that compare notepad entries to CRM delivery dates. Per PRD §3.6.

#### Acceptance Criteria
- [ ] Rule: If notepad shows delivered but CRM Delivery Date is blank → flag "Delivered not marked in CRM" (Severity: High)
- [ ] Rule: If CRM Delivery Date exists but notepad has no entry → flag "Delivered missing in notepad" (Severity: Medium/Low)
- [ ] Exception includes:
  - Severity level
  - Reason tags
  - Evidence (source fields and values)
  - Suggested action
- [ ] Support for date `D` delivery-day-close view

#### Technical Notes
- Consider timezone handling for date comparisons
- Generate actionable suggestions: "Mark delivered in CRM"

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx` for delivery dates

---

## Task ID: RECON-003
### Title: Payment Rules Engine (Order-Level)

**Priority**: P0  
**Estimated Effort**: 5 hours  
**Dependencies**: RECON-001, MATCH-003

#### Description
Implement order-level payment rules comparing CRM to notepad entries. Per PRD §3.7.1.

#### Acceptance Criteria
- [ ] Rule: Amount mismatch → Severity: High
- [ ] Rule: Mode mismatch but amount matches → Severity: Medium
- [ ] Rule: Duplicate notepad entries for same order → Severity: Medium/High
- [ ] Each exception includes:
  - Severity classification
  - Multiple reason tags
  - Evidence (source fields and values)
  - Suggested action (e.g., "Check if payment received", "Correct mode in CRM")
- [ ] Apply `AmountMatchToleranceINR` for matching

#### Technical Notes
- Handle multiple payment modes per order
- Consider partial payments in mismatch detection

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx` for payment data

---

## Task ID: RECON-004
### Title: Credit Policy Enforcement

**Priority**: P0  
**Estimated Effort**: 4 hours  
**Dependencies**: RECON-001, RECON-002

#### Description
Implement the no-credit policy rule that flags orders delivered with outstanding balance. Per PRD §3.8.

#### Acceptance Criteria
- [ ] Flag "Credit Policy Violation" (Severity: High) when:
  - Order is delivered (Delivery Date exists)
  - `BalanceDueAtDelivery > CreditToleranceINR` (default ₹1)
  - No notepad entry or payment event on/around delivery day settles balance
- [ ] Exception includes:
  - Balance amount
  - Delivery date
  - Last payment date
  - Suggested action

#### Technical Notes
- Consider "immediately around delivery day" as configurable window
- Check both notepad and payment events

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx` for balance data

---

## Task ID: RECON-005
### Title: Google Pay Validation (CRM vs MSWIPE Day Totals)

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: RECON-001, IMP-002, CFG-001

#### Description
Implement day-level Google Pay/UPI validation comparing CRM totals to MSWIPE totals. Per PRD §3.7.2.

#### Acceptance Criteria
- [ ] Compute `TotalGPay_CRM`: sum of CRM payments marked Google Pay for date `D`
  - Use Payment Date; fallback to Delivery Date if missing and amount > 0
- [ ] Compute `TotalGPay_MSWIPE`: sum of successful MSWIPE Google Pay/UPI for date `D`
- [ ] Apply day-level tolerance: max(DailyTotalToleranceINR, DailyTotalTolerancePercent)
- [ ] If `MSWIPE > CRM` beyond tolerance → flag "Missing or misclassified GPay entries in CRM"
- [ ] If `CRM > MSWIPE` beyond tolerance:
  - Flag "Possible paid-but-not-received, wrong mode, or duplicate in CRM"
  - Identify candidate problematic orders (CRM mode = GPay, no MSWIPE match)
  - Rank candidates by likelihood
- [ ] MSWIPE-to-order linking:
  - Attempt best-effort match by amount and time window (180 min default)
  - Treat as "probabilistic" if no order identifiers

#### Technical Notes
- Time window matching: `MSWIPETimeMatchWindowMinutes`
- Day totals are the strong truth signal from MSWIPE

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx` for CRM GPay
- `Mswipe-Transactions-November.csv` for MSWIPE totals

---

## Task ID: RECON-006
### Title: Cash Validation (Orders vs Cash Register)

**Priority**: P0  
**Estimated Effort**: 5 hours  
**Dependencies**: RECON-001, IMP-003, CFG-001

#### Description
Implement cash validation comparing expected cash from reconciled orders to cash register derived signal. Per PRD §3.7.3.

#### Acceptance Criteria
- [ ] Compute expected cash from orders marked Cash:
  - Prefer notepad for "collected on delivery" when CRM missing
  - Track confidence flag for source
- [ ] Derive cash signal: `CashFromOrders_d ≈ C_d - C_(d-1) + E_d`
- [ ] Compare expected vs derived cash
- [ ] Apply tolerance: max(CashVarianceToleranceINR, CashVarianceTolerancePercent)
- [ ] If variance exceeds tolerance → flag "Cash variance"
- [ ] Exception includes:
  - Expected cash amount
  - Derived cash signal
  - Variance amount
  - Confidence level

#### Technical Notes
- Handle "partial" validation when cash register data incomplete
- E_d (expenses) may need user input

#### Sample Data Reference
- `DailyCashRegister.xlsx` for cash balances

---

### MILESTONE 5: User Interface

---

## Task ID: UI-001
### Title: Import Wizard Screen

**Priority**: P0  
**Estimated Effort**: 8 hours  
**Dependencies**: IMP-001, IMP-002, IMP-003, IMP-004, IMP-005

#### Description
Implement the Import Wizard screen with all steps for importing data. Per PRD §4.1.

#### Acceptance Criteria
- [ ] Step 1: Select date or date range
- [ ] Step 2: Upload CRM file + column mapping + save profile
- [ ] Step 3: Upload MSWIPE file + column mapping
- [ ] Step 4: Upload Cash Register + select year sheet + map months/days + preview C_d
- [ ] Step 5: Enter notepad lines (grid) OR upload screenshot (if OCR enabled)
- [ ] Navigation: Back/Next between steps
- [ ] Progress indicator
- [ ] Validation before proceeding to next step
- [ ] "Run Reconciliation" button on final step

#### Technical Notes
- Consider wizard state persistence (resume on browser refresh)
- File upload with drag-and-drop
- Preview data after mapping before committing

#### Sample Data Reference
- All sample files for testing

---

## Task ID: UI-002
### Title: Reconciled Orders Results Table

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: RECON-006, UI-001

#### Description
Implement the Reconciled Orders table with filtering, sorting, and detailed views. Per PRD §4.1.

#### Acceptance Criteria
- [ ] Table displays all reconciled orders for selected date(s)
- [ ] Columns: Order Number, Customer, Amount, Payment Mode, Status, Severity, Actions
- [ ] Filter by: severity, payment mode, runner, marked-by
- [ ] Sort by any column
- [ ] Expandable row for full details and match explanation
- [ ] Color-coding by severity (High = red, Medium = yellow, Low = green)
- [ ] Pagination for large result sets

#### Technical Notes
- Consider virtual scrolling for 500+ orders
- Load match explanations on-demand for performance

#### Sample Data Reference
N/A

---

## Task ID: UI-003
### Title: Exceptions Queue with Resolve Actions

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: UI-002, MATCH-003

#### Description
Implement the Exceptions Queue with actionable resolve options. Per PRD §4.1.

#### Acceptance Criteria
- [ ] List all exceptions for reconciliation run
- [ ] Display: severity, reason, evidence, suggested action
- [ ] Resolve actions:
  - Link notepad entry to order (show candidates)
  - Mark as false positive (with reason)
  - Add manual note
  - Override match decision
- [ ] Filter by exception type and severity
- [ ] Bulk resolve similar exceptions
- [ ] All actions logged for audit

#### Technical Notes
- Integrate with MATCH-003 manual review queue
- Show before/after state for resolve actions

#### Sample Data Reference
N/A

---

## Task ID: UI-004
### Title: Daily Summary Dashboard

**Priority**: P0  
**Estimated Effort**: 5 hours  
**Dependencies**: RECON-005, RECON-006, UI-002

#### Description
Implement the Daily Summary view showing totals and variance comparisons. Per PRD §4.1.

#### Acceptance Criteria
- [ ] Totals by payment mode (CRM vs Notepad vs MSWIPE)
- [ ] Cash variance signal vs expected cash
- [ ] Google Pay variance display
- [ ] Total orders processed
- [ ] Total exceptions by severity
- [ ] Match rate statistics
- [ ] Visual indicators for variance status (OK, Warning, Alert)

#### Technical Notes
- Consider charts/graphs for visual clarity
- Export summary to PDF option (stretch)

#### Sample Data Reference
N/A

---

### MILESTONE 6: Export & Polish

---

## Task ID: EXP-001
### Title: Excel Workbook Export

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: RECON-006, UI-003

#### Description
Implement Excel workbook export with all required sheets. Per PRD §4.2.

#### Acceptance Criteria
- [ ] Export workbook with sheets:
  - `Reconciled_Orders`: all orders with status
  - `Exceptions`: all exceptions with reasons and suggested actions
  - `Unmatched_Notepad`: notepad entries without matches
  - `Unmatched_MSWIPE`: MSWIPE transactions without matches
  - `Daily_Summary`: totals and variance data
  - `Audit_Log`: import, match, and override history
- [ ] Each exception row has "reason" column with clear text (PRD §4.2)
- [ ] Proper column formatting (dates, currency, etc.)
- [ ] Auto-filter enabled on all sheets
- [ ] Filename includes date range

#### Technical Notes
- Use xlsxwriter or openpyxl for generation
- Consider conditional formatting for severity
- Handle large workbooks efficiently

#### Sample Data Reference
N/A - Generate from test reconciliation run

---

## Task ID: NFR-001
### Title: Error Handling & Input Validation

**Priority**: P1  
**Estimated Effort**: 5 hours  
**Dependencies**: IMP-005

#### Description
Implement comprehensive error handling with clear, user-friendly messages. Per PRD §5.2.

#### Acceptance Criteria
- [ ] Clear errors for: missing columns, unreadable files, invalid dates, unmapped modes
- [ ] Error messages include: what went wrong, where (file/row/column), how to fix
- [ ] Graceful degradation: continue processing valid rows when some fail
- [ ] Error summary report after import
- [ ] No stack traces shown to users
- [ ] All errors logged with full context for debugging

#### Technical Notes
- Create custom exception classes for each error type
- Consider error recovery options where possible

#### Sample Data Reference
- Create malformed test files for validation

---

## Task ID: NFR-002
### Title: Audit Logging Framework

**Priority**: P1  
**Estimated Effort**: 5 hours  
**Dependencies**: DATA-002

#### Description
Implement comprehensive audit logging for all system actions. Per PRD §5.2.

#### Acceptance Criteria
- [ ] Log every import with: timestamp, file name, row counts, user
- [ ] Log every match decision with: factors, scores, confidence, source records
- [ ] Log every manual override with: before/after state, user, reason
- [ ] Log every exception resolution with: action taken, user, timestamp
- [ ] Audit log queryable by date range, action type, user
- [ ] Audit log exportable (included in Excel export)

#### Technical Notes
- Use structured logging (JSON format)
- Consider log rotation for long-running systems
- Ensure audit entries are immutable

#### Sample Data Reference
N/A

---

## Task ID: OPT-001
### Title: OCR for Notepad Screenshots (Optional Feature)

**Priority**: P2  
**Estimated Effort**: 8 hours  
**Dependencies**: IMP-004

#### Description
Implement optional OCR feature to extract notepad data from screenshots. Per PRD §2.2 (behind a toggle).

#### Acceptance Criteria
- [ ] Feature toggle to enable/disable OCR
- [ ] Upload screenshot image (JPEG, PNG)
- [ ] Use pytesseract to extract text
- [ ] Parse extracted text into notepad fields
- [ ] Pre-fill notepad entry grid with OCR results
- [ ] User must review and confirm before saving
- [ ] Handle OCR errors gracefully with manual fallback

#### Technical Notes
- May require Tesseract installation on user machine
- Consider confidence scores for OCR results
- Support common notepad layouts (may need training)

#### Sample Data Reference
- Create sample notepad screenshots for testing

---

### MILESTONE 7: Testing

---

## Task ID: TEST-001
### Title: Unit Tests — Data Layer & Configuration

**Priority**: P0  
**Estimated Effort**: 5 hours  
**Dependencies**: DATA-001, DATA-002, CFG-001

#### Description
Implement comprehensive unit tests for all data layer components including database schema, repository methods, and configuration management.

#### Acceptance Criteria
- [ ] Unit tests for `OrderRepository`: CRUD operations, query by date range, duplicate handling
- [ ] Unit tests for `PaymentEventRepository`: linking to orders, date filters, JSON serialization
- [ ] Unit tests for `DeliveryEventRepository`: source tracking, conflict detection
- [ ] Unit tests for `ReconciliationRunRepository`: snapshot creation, audit queries
- [ ] Unit tests for configuration loading, validation, and per-run overrides
- [ ] Unit tests for payment mode mapping normalization
- [ ] Test database isolation (each test uses clean database)
- [ ] Edge cases: null values, invalid data types, constraint violations
- [ ] Code coverage target: ≥ 90% for data layer modules

#### Technical Notes
- Use pytest with fixtures for database setup/teardown
- Use SQLite in-memory database for fast tests
- Mock external dependencies where needed

#### Sample Data Reference
- Create test fixtures based on sample data structure

---

## Task ID: TEST-002
### Title: Unit Tests — Import Pipeline

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: IMP-001, IMP-002, IMP-003, IMP-004, IMP-005

#### Description
Implement unit tests for all import parsers covering normalization rules, column mapping, and error handling.

#### Acceptance Criteria
- [ ] CRM Parser tests:
  - [ ] Valid Excel/CSV parsing
  - [ ] Date format variations (DD/MM/YYYY, MM-DD-YYYY, etc.)
  - [ ] Amount parsing (₹1,234.56, 1234, "1,234")
  - [ ] Payment mode normalization
  - [ ] Adjustments interpretation
  - [ ] Missing required columns error
- [ ] MSWIPE Parser tests:
  - [ ] Successful transaction filtering
  - [ ] Day-bucketing with timezone
  - [ ] Amount field precedence (FinalPayment > NetAmt > TxnAmt)
  - [ ] GPay/UPI identification from various fields
  - [ ] Auto-column detection
- [ ] Cash Register Parser tests:
  - [ ] Calendar grid extraction
  - [ ] Cross-month lookups
  - [ ] 5-day lookback for missing data
  - [ ] Derived signal calculation
- [ ] Notepad Entry tests:
  - [ ] Field validation
  - [ ] CRUD operations
- [ ] Column Mapping Engine tests:
  - [ ] Auto-detection accuracy
  - [ ] Profile save/load
  - [ ] Validation rules
- [ ] Code coverage target: ≥ 85% for import modules

#### Technical Notes
- Create test files with known edge cases
- Test both valid and malformed inputs
- Verify error messages are user-friendly

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx`
- `Mswipe-Transactions-November.csv`
- `DailyCashRegister.xlsx`
- Create additional edge-case test files

---

## Task ID: TEST-003
### Title: Unit Tests — Matching Engine

**Priority**: P0  
**Estimated Effort**: 5 hours  
**Dependencies**: MATCH-001, MATCH-002, MATCH-003

#### Description
Implement unit tests for the matching engine covering exact matching, fuzzy matching, and confidence scoring.

#### Acceptance Criteria
- [ ] Exact matching tests:
  - [ ] Case-insensitive order number matching
  - [ ] Whitespace normalization
  - [ ] Leading zeros handling
  - [ ] Duplicate detection
- [ ] Fuzzy matching tests:
  - [ ] Name similarity scoring (Hindi/English variations)
  - [ ] Amount tolerance boundaries (₹2 threshold)
  - [ ] Date proximity scoring
  - [ ] Combined weighted scoring
- [ ] Confidence scoring tests:
  - [ ] Score calculation for various factor combinations
  - [ ] Threshold-based routing (auto vs manual review)
  - [ ] Explanation generation accuracy
- [ ] Edge cases:
  - [ ] No match found
  - [ ] Multiple candidates with similar scores
  - [ ] Empty/null fields
- [ ] Code coverage target: ≥ 90% for matching modules

#### Technical Notes
- Use parameterized tests for threshold boundary testing
- Mock fuzzy matching library for deterministic tests
- Test with realistic name variations from sample data

#### Sample Data Reference
- Extract customer names from `SalesAndDeliveryCRMExport-November.xlsx`

---

## Task ID: TEST-004
### Title: Unit Tests — Reconciliation Rules

**Priority**: P0  
**Estimated Effort**: 6 hours  
**Dependencies**: RECON-001, RECON-002, RECON-003, RECON-004, RECON-005, RECON-006

#### Description
Implement unit tests for all reconciliation rules including order ledger, delivery status, payment rules, and validations.

#### Acceptance Criteria
- [ ] Order Mini-Ledger tests:
  - [ ] TotalPaidToDate calculation with multiple payments
  - [ ] Advance payment detection (PaymentDate < DeliveryDate)
  - [ ] Balance calculation
  - [ ] Cross-date payment accumulation
- [ ] Delivery Status Rule tests:
  - [ ] "Delivered not marked in CRM" detection
  - [ ] "Delivered missing in notepad" detection
  - [ ] Severity assignment
- [ ] Payment Rules tests:
  - [ ] Amount mismatch detection (within/outside tolerance)
  - [ ] Mode mismatch detection
  - [ ] Duplicate notepad entry detection
- [ ] Credit Policy tests:
  - [ ] Violation detection when balance > tolerance
  - [ ] No violation when fully paid via advance
- [ ] GPay Validation tests:
  - [ ] Day-total calculations for CRM and MSWIPE
  - [ ] Variance detection with tolerance
  - [ ] Candidate order identification
- [ ] Cash Validation tests:
  - [ ] Derived signal calculation
  - [ ] Variance detection with tolerance
  - [ ] Partial validation handling
- [ ] Code coverage target: ≥ 90% for reconciliation modules

#### Technical Notes
- Create test scenarios for each business rule
- Test tolerance boundary conditions
- Verify exception severity and reason accuracy

#### Sample Data Reference
- Create synthetic order/payment scenarios

---

## Task ID: TEST-005
### Title: Integration Tests — End-to-End Reconciliation Flow

**Priority**: P0  
**Estimated Effort**: 8 hours  
**Dependencies**: TEST-001, TEST-002, TEST-003, TEST-004

#### Description
Implement integration tests that verify the complete reconciliation flow from file import through exception generation and export.

#### Acceptance Criteria
- [ ] Full pipeline test: Import → Match → Reconcile → Export
- [ ] Test with sample data files:
  - [ ] Import CRM, MSWIPE, Cash Register files
  - [ ] Enter notepad entries
  - [ ] Run reconciliation
  - [ ] Verify expected matches and exceptions
- [ ] Cross-date scenarios:
  - [ ] Advance payment on Day 1, delivery on Day 3
  - [ ] Multiple partial payments across days
- [ ] Exception verification:
  - [ ] Correct severity levels
  - [ ] Accurate evidence in exceptions
  - [ ] Proper suggested actions
- [ ] Export verification:
  - [ ] All sheets present with correct data
  - [ ] Audit log completeness
- [ ] Performance test:
  - [ ] 500 orders processed in < 30 seconds (PRD §5.2)
- [ ] Error recovery:
  - [ ] Partial import success (some rows fail)
  - [ ] Resume after interruption

#### Technical Notes
- Use real sample files for realistic testing
- Create golden output files for regression testing
- Measure and assert performance metrics

#### Sample Data Reference
- `SalesAndDeliveryCRMExport-November.xlsx`
- `Mswipe-Transactions-November.csv`
- `DailyCashRegister.xlsx`

---

## Task ID: TEST-006
### Title: Integration Tests — User Interface

**Priority**: P1  
**Estimated Effort**: 6 hours  
**Dependencies**: UI-001, UI-002, UI-003, UI-004, TEST-005

#### Description
Implement integration tests for all UI screens verifying user workflows and data display.

#### Acceptance Criteria
- [ ] Import Wizard tests:
  - [ ] Step navigation (forward/back)
  - [ ] File upload handling
  - [ ] Column mapping interaction
  - [ ] Validation blocking progression
  - [ ] Reconciliation trigger
- [ ] Results Table tests:
  - [ ] Data display accuracy
  - [ ] Filtering by severity, mode, runner
  - [ ] Sorting by columns
  - [ ] Row expansion for details
  - [ ] Pagination
- [ ] Exceptions Queue tests:
  - [ ] Exception display
  - [ ] Resolve action flows (link, false positive, note)
  - [ ] Audit logging of resolutions
- [ ] Daily Summary tests:
  - [ ] Totals accuracy
  - [ ] Variance display
  - [ ] Visual indicators
- [ ] Accessibility:
  - [ ] Keyboard navigation
  - [ ] Screen reader compatibility (basic)

#### Technical Notes
- Use UI testing framework (pytest + selenium/playwright, or equivalent)
- Test with realistic data volumes
- Capture screenshots for visual regression

#### Sample Data Reference
- Results from TEST-005 integration tests

---

## Task ID: TEST-007
### Title: Integration Tests — Error Handling & Audit

**Priority**: P1  
**Estimated Effort**: 4 hours  
**Dependencies**: NFR-001, NFR-002, TEST-005

#### Description
Implement integration tests for error handling, validation messages, and audit log integrity.

#### Acceptance Criteria
- [ ] Error handling tests:
  - [ ] Missing required columns shows clear error
  - [ ] Invalid date formats show location and expected format
  - [ ] Unmapped payment modes show actionable message
  - [ ] Malformed Excel files handled gracefully
  - [ ] No stack traces visible to user
- [ ] Graceful degradation:
  - [ ] Valid rows processed when some fail
  - [ ] Error summary report accurate
- [ ] Audit log tests:
  - [ ] Every import logged with metadata
  - [ ] Every match decision recorded
  - [ ] Every manual override captured
  - [ ] Log entries are immutable
  - [ ] Log export includes all entries
- [ ] Log queryability:
  - [ ] Filter by date range
  - [ ] Filter by action type
  - [ ] Filter by user

#### Technical Notes
- Create intentionally malformed test files
- Verify log entries match expected schema
- Test audit log performance with large volumes

#### Sample Data Reference
- Create edge-case and error-case test files

---

## PRD Section Coverage Verification

| PRD Section | Tasks Covering |
|-------------|---------------|
| §2.1 CRM Import | IMP-001, IMP-005 |
| §2.2 Notepad Entry | IMP-004, OPT-001 |
| §2.3 MSWIPE Import | IMP-002, IMP-005 |
| §2.4 Cash Register | IMP-003 |
| §3.1 Core Concepts | DATA-001 |
| §3.2 Tolerances | CFG-001 |
| §3.3 Storage Model | DATA-001, DATA-002 |
| §3.4 Matching Strategy | MATCH-001, MATCH-002, MATCH-003 |
| §3.5 Advance Payments | RECON-001 |
| §3.6 Delivery Status | RECON-002 |
| §3.7.1 Payment Rules | RECON-003 |
| §3.7.2 GPay Validation | RECON-005 |
| §3.7.3 Cash Validation | RECON-006 |
| §3.8 Credit Policy | RECON-004 |
| §3.9 Severity | RECON-002, RECON-003, RECON-004, RECON-005, RECON-006 |
| §4.1 Screens | UI-001, UI-002, UI-003, UI-004 |
| §4.2 Exports | EXP-001 |
| §5.1 Tech Stack | DATA-001 |
| §5.2 NFRs | NFR-001, NFR-002 |
| §5.3 Acceptance | All tasks combined |

---

## Total Effort Summary

| Category | Tasks | Estimated Hours |
|----------|-------|-----------------|
| Data Layer | DATA-001, DATA-002, CFG-001 | 15 hours |
| Import Pipeline | IMP-001 to IMP-005 | 30 hours |
| Matching Engine | MATCH-001 to MATCH-003 | 15 hours |
| Reconciliation | RECON-001 to RECON-006 | 30 hours |
| User Interface | UI-001 to UI-004 | 25 hours |
| Export & Polish | EXP-001, NFR-001, NFR-002, OPT-001 | 24 hours |
| Testing | TEST-001 to TEST-007 | 40 hours |
| **TOTAL** | **31 tasks** | **179 hours** |

---

*Generated by Planning Agent based on PRD.md analysis*
