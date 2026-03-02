# Laundry Reconciler MVP

Automates daily reconciliation of laundry business sales and delivery data from CRM, MSWIPE, cash register, and runner notepad sources. Matches orders to payments, flags discrepancies (including late payments) as severity-classified exceptions, and exports Excel reconciliation reports.

---

## Features

- **CRM 3-report import** — Sales Report (payment transactions), Orders Report (authoritative amounts), Delivery Report (delivery dates)
- **Multi-payment order aggregation** — Correctly handles orders with multiple payment rows (advance, delivery, post-delivery)
- **Late payment detection** — Flags payments made after delivery with configurable threshold
- **Smart matching** — Exact order-number matching + fuzzy matching (name, amount, date) with confidence scoring
- **Guided import wizard** — Step-by-step Streamlit UI with progress tracking and data previews
- **Manual notepad entry** — Web form to enter runner delivery data without needing Excel files
- **Reconciliation rules** — Delivery status, payment accuracy, credit policy, GPay totals, cash variance, late payments
- **Exception management** — Severity-classified exceptions with evidence, suggested actions, and resolution workflow
- **Excel export** — 6-sheet workbook: Reconciled Orders, Exceptions, Unmatched Notepad, Unmatched MSWIPE, Daily Summary, Audit Log
- **External config** — `.env` file support via pydantic-settings for all tolerances and mappings
- **File validation** — Type whitelist, size limits (50 MB), and path traversal prevention on all imports

---

## Exception Categories & Rules

The reconciliation engine automatically flags discrepancies across the imported data sources. Here are the 7 exception scenarios it detects:

| Exception Type | Severity | Firing Rule | Action Required |
| --- | --- | --- | --- |
| **DeliveredNotMarkedCRM** | 🔴 High | Order is marked as delivered in the Runner Notepad, but has no corresponding Delivery Event in CRM. | Mark the order as delivered in CRM. |
| **DeliveredMissingNotepad** | 🟡 Medium | Order has a Delivery Event in CRM, but is missing from the Runner Notepad for that date. | Check runner notepad for missing entry. |
| **CreditPolicyViolation** | 🔴 High | Order is delivered, but the outstanding balance exceeds the configured `CREDIT_TOLERANCE_INR` (default: ₹1.00). | Collect pending payment from customer. |
| **NotepadAmountMismatch** | 🟡 Medium | The amount collected according to the Notepad differs from the CRM payment by more than `AMOUNT_MATCH_TOLERANCE_INR` (default: ₹2.00). | Review notepad entry. CRM amount is treated as authoritative. |
| **GPayMismatch** | 🔴 High / 🟡 Medium | Total GPay amount recorded in CRM for the day differs from MSWIPE total by more than `GPAY_TOLERANCE_INR` (default: ₹10.00). *High severity if variance > ₹100.* | Investigate GPay day-total discrepancy. |
| **CashVariance** | 🔴 High | Total Cash recorded in Notepad for the day differs from the derived cash in the Cash Register by more than `CASH_VARIANCE_TOLERANCE_INR` (default: ₹100.00). | Check cash register for missing deposits/expenses. |
| **LatePayment** | 🟡 Medium | A payment is received after the delivery date by more than `LATE_PAYMENT_THRESHOLD_DAYS` (default: 0 days). | Review late payment receipt. |

---

## Prerequisites

- **Python 3.9+**
- **pip** (comes with Python)
- **Git** (for cloning)

---

## Local Setup

### Option A: Quick Setup (Recommended)

**Windows:**
```cmd
setup.bat
```

**macOS / Linux:**
```bash
chmod +x setup.sh
./setup.sh
```

These scripts create a virtual environment, install dependencies, and initialize the database.

### Option B: Manual Setup

```bash
git clone <repository-url>
cd laundry-reconciler-docs
python -m venv venv

# Activate (choose your shell):
.\venv\Scripts\Activate.ps1          # PowerShell
.\venv\Scripts\activate.bat          # CMD
source venv/bin/activate             # macOS/Linux

pip install -r requirements.txt
python -m src.cli init-db
```

### Configuration (Optional)

Copy `.env.example` to `.env` and uncomment settings you want to override:
```bash
cp .env.example .env
```

---

## Usage

### Streamlit Web UI (Recommended)

```bash
streamlit run src/ui/app.py --server.address localhost
```

Opens a browser at `http://localhost:8501` with:
- **Import Wizard** — 6-step guided flow with progress bar:
  1. CRM Sales Report *(required first)*
  2. CRM Orders Report
  3. CRM Delivery Report
  4. MSWIPE Transactions
  5. Runner Notepad *(file upload or manual entry form)*
  6. Cash Register
- **Run Reconciliation** — Select a date and run matching + rules engine
- **View Results** — Browse exceptions with severity/type/status filters
- **History** — View past reconciliation runs

### Command-Line Interface

```bash
# Import data (recommended order: Sales → Orders → Delivery → others)
python -m src.cli import-crm path/to/sales.xlsx
python -m src.cli import-crm-orders path/to/orders.xlsx
python -m src.cli import-crm-delivery path/to/delivery.xlsx
python -m src.cli import-mswipe path/to/mswipe.csv
python -m src.cli import-notepad path/to/notepad.xlsx
python -m src.cli import-cash path/to/register.xlsx --year 2025

# Run reconciliation
python -m src.cli reconcile 2025-11-15
python -m src.cli reconcile 2025-11-15 --export
```

> **Note:** Use `python -m src.cli` (not `python src/cli.py`). The `-m` flag ensures proper module resolution.

### Typical Workflow

1. **Import** CRM Sales, Orders, and Delivery reports for the month
2. **Import** MSWIPE, Notepad, and Cash Register data for the day
3. **Run reconciliation** for the target date
4. **Review exceptions** in the UI or exported Excel
5. **Resolve issues** — mark as resolved or false positive with notes

---

## Running Tests

```bash
python -m pytest tests/ -v                                 # All tests
python -m pytest tests/test_crm_importer.py -v             # Specific file
python -m pytest tests/ --cov=src --cov-report=term-missing # With coverage
```

### Test Suite (39 tests)

| File | Coverage |
|------|----------|
| `test_db.py` | Order CRUD, defaults, `__repr__` |
| `test_repositories.py` | OrderRepo, PaymentRepo, DeliveryRepo, date-range queries |
| `test_crm_importer.py` | CRM import: normalize, save, multi-row aggregation, integration |
| `test_mswipe_importer.py` | MSWIPE import pipeline |
| `test_notepad_importer.py` | Notepad import pipeline |
| `test_cash_register_importer.py` | Cash register import pipeline |
| `test_matching.py` | Exact + fuzzy matching |
| `test_reconciliation.py` | Reconciliation rules engine |
| `test_excel_exporter.py` | Export validation, error handling |
| `test_error_paths.py` | Edge cases: empty data, missing fields, no-data reconciliation |

---

## Project Structure

```
laundry-reconciler-docs/
├── src/
│   ├── cli.py                      # CLI (7 import commands + reconcile)
│   ├── exceptions.py               # Custom exception hierarchy
│   ├── config/settings.py          # pydantic-settings (BaseSettings, .env support)
│   ├── db/
│   │   ├── base.py                 # SQLAlchemy declarative base
│   │   └── init_db.py              # Database init with path sanitization
│   ├── exporters/
│   │   └── excel_exporter.py       # 6-sheet Excel workbook generation
│   ├── importers/
│   │   ├── base.py                 # Abstract BaseImporter with transaction rollback
│   │   ├── crm.py                  # CRM Sales: multi-payment aggregation
│   │   ├── crm_delivery.py         # CRM Delivery: delivery dates & piece counts
│   │   ├── crm_orders.py           # CRM Orders: authoritative Net Amount
│   │   ├── mswipe.py               # MSWIPE transaction parser
│   │   ├── cash_register.py        # Cash register calendar grid parser
│   │   └── notepad.py              # Runner notepad parser
│   ├── models/                     # SQLAlchemy ORM models (all with __repr__)
│   ├── repositories/               # Data access layer (Repository pattern)
│   ├── services/
│   │   ├── matching.py             # Batch matching with confidence explanations
│   │   └── reconciliation.py       # Rules: delivery, credit, late payments, gpay, cash
│   └── ui/
│       ├── app.py                  # Streamlit: guided wizard + manual notepad entry
│       └── styles.css              # Custom CSS: step cards, progress bar, badges
├── sample/                         # Sample CRM reports (November 2025)
├── tests/                          # 39 pytest tests
│   └── conftest.py                 # Shared fixtures (in-memory SQLite)
├── .env.example                    # All configurable settings (copy to .env)
├── setup.bat / setup.sh            # Quick setup scripts
├── requirements.txt                # Pinned Python dependencies
├── PRD.md / PLAN.md                # Product requirements & implementation plan
└── AGENTS.md                       # AI agent/developer context
```

---

## Configuration

All settings can be overridden via `.env` file or environment variables (pydantic-settings):

| Setting | Default | Description |
|---------|---------|-------------|
| `AMOUNT_MATCH_TOLERANCE_INR` | 2.00 | Max acceptable payment mismatch (₹) |
| `DATE_WINDOW_DAYS` | 3 | Days to look forward/backward for matching |
| `FUZZY_NAME_THRESHOLD` | 0.82 | Min name similarity for fuzzy match |
| `CREDIT_TOLERANCE_INR` | 1.00 | Max unpaid balance before credit violation |
| `CASH_VARIANCE_TOLERANCE_INR` | 100.00 | Cash register variance threshold (₹) |
| `GPAY_TOLERANCE_INR` | 10.00 | GPay day-total mismatch threshold (₹) |
| `LATE_PAYMENT_THRESHOLD_DAYS` | 0 | Days after delivery before flagging late payment |
| `CONFIDENCE_AUTO_ACCEPT` | 0.85 | Auto-accept matches above this score |
| `CONFIDENCE_REVIEW_THRESHOLD` | 0.60 | Flag for manual review above this score |

**Payment mode mapping:** Cash, GPay (Google Pay/UPI), Paytm (Online), Package, Card

---

## Security

- **Localhost-only** — Streamlit UI binds to `localhost` (no network exposure)
- **File validation** — Type whitelist, 50 MB size limit, path traversal prevention
- **DB path sanitization** — Regex whitelist prevents SQL injection via database path
- **Pinned dependencies** — All versions pinned in `requirements.txt`
- **Transaction rollback** — Failed imports are fully rolled back
- **Cascade-safe deletes** — Repository delete catches integrity violations and rolls back

---

## License

Private — Internal use only.
