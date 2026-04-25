# System Architecture — Laundry Reconciler MVP

## 1. System Overview

The Laundry Reconciler is a local-first desktop application that automates daily reconciliation of laundry orders by importing data from multiple sources, matching orders with payments, and flagging exceptions for quick resolution.

### System Context Diagram

```mermaid
graph TB
    subgraph External Actors
        User["Store Owner/Manager"]
    end
    
    subgraph Data Sources
        CRM["CRM Export<br/>(Excel/CSV)"]
        MSWIPE["MSWIPE Transactions<br/>(CSV)"]
        CashReg["Cash Register<br/>(Excel Grid)"]
        Notepad["Runner Notepad<br/>(Manual Entry)"]
    end
    
    subgraph Laundry Reconciler
        App["Laundry Reconciler<br/>Application"]
    end
    
    subgraph Outputs
        Excel["Excel Workbook<br/>(6 sheets)"]
        DB["SQLite Database<br/>(History + Audit)"]
    end
    
    User -->|"Import & Review"| App
    CRM --> App
    MSWIPE --> App
    CashReg --> App
    Notepad --> App
    App --> Excel
    App --> DB
```

---

## 2. Component Architecture

### High-Level Component Diagram

```mermaid
graph TB
    subgraph Presentation Layer
        UI["UI Layer<br/>(Import Wizard, Results, Exceptions)"]
    end
    
    subgraph Application Layer
        IS["Import Service"]
        RS["Reconciliation Service"]
        ES["Export Service"]
        CS["Config Service"]
    end
    
    subgraph Domain Layer
        NE["Normalizer Engine"]
        ME["Matching Engine"]
        RE["Rule Engine"]
    end
    
    subgraph Data Layer
        REPO["Repository Layer"]
        DB[(SQLite Database)]
    end
    
    UI --> IS
    UI --> RS
    UI --> ES
    UI --> CS
    
    IS --> NE
    RS --> ME
    RS --> RE
    
    IS --> REPO
    RS --> REPO
    ES --> REPO
    CS --> REPO
    
    REPO --> DB
```

### Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **UI Layer** | Import wizard screens, results display, exception queue, daily summary |
| **Import Service** | File ingestion, column mapping, validation, data persistence |
| **Reconciliation Service** | Orchestrates matching and rule execution for a date |
| **Export Service** | Generates Excel workbook with 6 sheets |
| **Config Service** | Manages tolerances, mapping profiles, settings |
| **Normalizer Engine** | Date parsing, amount parsing, payment mode standardization |
| **Matching Engine** | Order-payment-delivery matching with confidence scoring |
| **Rule Engine** | Business rule execution, exception generation, severity classification |
| **Repository Layer** | Data access abstraction over SQLite |

---

## 3. Data Flow

### End-to-End Reconciliation Flow

```mermaid
flowchart LR
    subgraph Input
        A1[CRM Export] --> B[Import Service]
        A2[MSWIPE CSV] --> B
        A3[Cash Register] --> B
        A4[Notepad Entry] --> B
    end
    
    B --> C[Normalize]
    C --> D[Persist to SQLite]
    
    subgraph Processing
        D --> E[Match Orders ↔ Payments ↔ Deliveries]
        E --> F[Apply Business Rules]
        F --> G[Generate Exceptions]
        G --> H[Compute Summaries]
    end
    
    subgraph Output
        H --> I[Display Results]
        H --> J[Export Workbook]
    end
```

### Cross-Date Processing

The system maintains history across dates to handle:
- **Advance payments**: Payment recorded days before delivery
- **Partial payments**: Multiple payments for same order over time
- **Order mini-ledger**: Running balance per order (OrderAmount - TotalPaidToDate)

```mermaid
sequenceDiagram
    participant Day1 as Day D-3
    participant Day2 as Day D (Reconciliation)
    participant DB as SQLite
    
    Day1->>DB: Store advance payment (₹500)
    Note over Day1,DB: PaymentDate < DeliveryDate
    
    Day2->>DB: Import CRM (Order delivered, Payment=0)
    Day2->>DB: Query order history
    DB-->>Day2: TotalPaidToDate = ₹500
    Day2->>Day2: BalanceDue = OrderAmount - 500
    Note over Day2: No exception if fully paid
```

---

## 4. Technology Stack

### Decision: Technology Choices

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Language** | Python 3.10+ | PRD requirement; rich ecosystem for data processing |
| **Data Store** | SQLite | ACID compliance, JSON columns, zero-config, widely available |
| **Excel Parsing** | pandas + openpyxl | Robust Excel/CSV handling, DataFrame operations |
| **Fuzzy Matching** | rapidfuzz | Fast fuzzy string matching (Levenshtein, token_set_ratio) |
| **Date Parsing** | python-dateutil | Handles multiple date formats robustly |
| **Excel Export** | xlsxwriter | Multi-sheet workbook generation with formatting |
| **OCR (optional)** | pytesseract | Notepad screenshot parsing (behind feature toggle) |

### Decision: SQLite over TinyDB

**Context**: Need to persist reconciliation history across dates, support complex queries for cross-date lookups.

**Options Considered**:
- SQLite: RDBMS with JSON support
- TinyDB: Document store
- LMDB/RocksDB: Key-value stores

**Decision**: SQLite

**Rationale**:
1. ACID compliance for data integrity during reconciliation
2. JSON column support (`json_extract()`) for flexible event storage
3. Rich query capabilities for cross-date payment lookups
4. Zero external dependencies; single-file database
5. Better performance for indexed queries on 500+ orders/day

---

## 5. Deployment Model

### Local-First Architecture

```mermaid
graph LR
    subgraph User Machine
        App["Python Application"]
        DB["SQLite DB<br/>(~/.laundry-reconciler/data.db)"]
        Config["Config Files<br/>(~/.laundry-reconciler/config.json)"]
    end
    
    App --> DB
    App --> Config
```

**Characteristics**:
- No server or network required
- All data stored locally
- Single-user desktop application
- Portable: database is a single file

### File System Layout

```
~/.laundry-reconciler/
├── data.db                 # SQLite database
├── config.json             # User settings, tolerances
├── mappings/               # Saved column mapping profiles
│   ├── crm-default.json
│   └── mswipe-default.json
├── exports/                # Generated workbooks
│   └── reconciliation-2025-11-29.xlsx
└── logs/                   # Application logs
    └── app.log
```

---

## 6. Security Considerations

| Concern | Design Decision |
|---------|-----------------|
| **Secrets** | No secrets required for MVP (local-only). Future: use environment variables or OS keychain. |
| **Data at Rest** | SQLite file on local disk; user responsible for disk encryption if needed. |
| **Sensitive Fields** | Customer mobile numbers stored but not displayed in exports unless required. |
| **Audit Trail** | Immutable audit log records all actions with timestamps. |

---

## 7. Extensibility Points

The architecture supports future enhancements:

| Extension Point | Mechanism |
|-----------------|-----------|
| **New data sources** | Implement `DataSourceParser` interface |
| **New matching strategies** | Add to matcher plugin chain |
| **New business rules** | Register rules with Rule Engine |
| **Runner direct entry** | Add mobile/web UI calling same services |
| **Cloud sync** | Replace SQLite with cloud-backed store |

---

## 8. Key Design Decisions Summary

| Decision | Choice | Key Rationale |
|----------|--------|---------------|
| Data Store | SQLite | ACID, JSON columns, zero-config |
| Matching | Exact → Fuzzy → Probabilistic | Per PRD §3.4 priority order |
| History | Cross-date persistence | Required for advance payment tracking |
| Rule Engine | Priority-based | Rules execute in defined order |
| Export | Single Excel workbook | 6 sheets per PRD §4.2 |
| Deployment | Local-first | No server, single-user, portable |

---

## 9. Low-Level Design (LLD)

### Database Schema (SQLAlchemy ORM)
The data layer is built on `SQLAlchemy` using an SQLite backing store. Key models include:
- **`Order`**: Master record of a transaction (`order_number`, `customer_name`, `net_amount`, `due_date`, `status`).
- **`PaymentEvent`**: Records individual financial interactions linked to an order. Tracks `amount`, `payment_date`, `payment_mode`, and `source` (`crm`, `mswipe`, `notepad`).
- **`DeliveryEvent`**: Records logistical fulfillment. Tracks `delivery_date`, `runner_name`, and `source` (`crm`, `notepad`).
- **`CashRegisterEntry`**: Daily summary imported from the physical register (`entry_date`, `derived_cash_from_orders`, `total_cash_in_register`).
- **`Expense`**: Legitimate business outflows (`expense_date`, `amount`, `category`, `mode`, `paid_to`). Adjusts net cash expectations.
- **`OrderException`**: Generated by the rule engine. Stores `severity`, `exception_type`, `evidence` (JSON), and `resolution_status`.
- **`ReconciliationRun`**: Audit wrapper tracking the execution of the reconciliation engine per date.

### Class Hierarchy & Importers
- **`BaseImporter`**: Abstract base class defining the standard ingestion pipeline:
  1. `import_data(file_path)`: Reads Excel/CSV into dictionaries.
  2. `normalize(raw_data)`: Standardizes dates (handling Indian `DD/MM/YYYY`), currency symbols, and text capitalization.
  3. `validate(data)`: Filters out invalid rows (e.g., missing dates, negative amounts).
  4. `save(data)`: Persists to the database using idempotent strategies.
- **Implementations**:
  - `CRMSalesImporter`: Uses Upsert strategy for orders. Aggregates multiple payment lines per order.
  - `NotepadImporter` & `MSwipeImporter`: Use Delete-by-Date strategies. Re-imports safely clear target dates before inserting.
  - `ExpensesImporter`: Uses Delete-by-Date. Extracts intelligent modes (`Cash`, `Online`, `Card`) with substring fallback logic.

### Reconciliation Engine Internals (`ReconciliationService`)
The `run_reconciliation(date)` method orchestrates the evaluation of logic rules for a specific date:

1. **`_initialize_run`**: Creates a `ReconciliationRun` audit entity. Clears old exceptions for the given run date.
2. **Order Level Rules (`_check_order_rules`)**:
   - Loops over orders delivered on `run_date`.
   - Compares total payments against order totals to flag `CreditPolicyViolation`.
   - Checks delivery synchronicity between CRM and Notepad (`DeliveredNotMarkedCRM`, `DeliveredMissingNotepad`).
3. **Cash Math & Variance Rules**:
   - **`_check_cash_variance`**: `Notepad Cash` - (`Register Cash` + `Cash Expenses`). Flags if variance > tolerance.
   - **`_check_crm_cash_vs_register`**: `CRM Cash` - (`Register Cash` + `Cash Expenses`). Explicit fraud rule ignoring Notepad.
4. **GPay Math & MSwipe Rules**:
   - Compares sum of CRM GPay/UPI to MSWIPE transactions.
   - Triggers `_check_backdated_payments` if variances exist, looking backward `N` days to locate delayed swipe sweeps (`BackdatedGPayPayment`).
5. **Cross-Date Correlation**:
   - **`_check_late_payments`**: If a CRM payment comes in > `LATE_PAYMENT_THRESHOLD_DAYS` after delivery.
   - **`_check_ageing_orders`**: Identifies active balances older than `AGEING_THRESHOLD` with no delivery.

### Configuration & Normalization
- **`Settings` (Pydantic)**: Defines robust, default-backed configuration parameters (`amount_match_tolerance_inr`, `fuzzy_name_min_score`, `cash_variance_tolerance_inr`). Configurable via `.env`.
- **Intelligent Mode Normalization**: Translates raw edge-cases like "Cash-adv", "gpay to counter", "swipe" into standardized programmatic enums (`Cash`, `GPay`, `Card`) using regex/substring mappings to improve resilience.
