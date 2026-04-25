# Laundry Reconciler MVP

Automates daily reconciliation of laundry business sales and delivery data from CRM, MSWIPE, cash register, and runner notepad sources. Matches orders to payments, flags discrepancies (including late payments) as severity-classified exceptions, and exports Excel reconciliation reports.

**Documentation Links:**
- [System Architecture & LLD](docs/ARCHITECTURE.md)
- [Detailed Features List](docs/FEATURES.md)

---

## Features

- **CRM 3-report import** — Sales Report (payment transactions), Orders Report (authoritative amounts), Delivery Report (delivery dates)
- **Multi-payment order aggregation** — Correctly handles orders with multiple payment rows (advance, delivery, post-delivery)
- **Late payment & Fraud detection** — Flags payments made after delivery and cross-references register surpluses to detect hidden cash pocketing.
- **Expenses Tracking** — Native integration of business expenses to cleanly offset counter cash variances without false alarms.
- **Smart matching & Substring mapping** — Exact order-number matching + fuzzy matching (name, amount, date) + intelligent mode parsing (e.g., mapping "cash adv" to "Cash").
- **Guided import wizard** — Step-by-step Streamlit UI with progress tracking, 7 stages of ingestion, and data previews.
- **Manual notepad entry** — Web form to enter runner delivery data without needing Excel files.
- **Reconciliation rules** — Delivery status, payment accuracy, credit policy, GPay totals, net cash variance (Notepad vs Register & CRM vs Register).
- **Exception management** — Severity-classified exceptions with evidence, suggested actions, and period-level "Self-Correcting" netting.
- **Excel export** — 6-sheet workbook: Reconciled Orders, Exceptions, Unmatched Notepad, Unmatched MSWIPE, Daily Summary, Audit Log.
- **External config** — `.env` file support via pydantic-settings for all tolerances and mappings.
- **File validation** — Type whitelist, size limits (50 MB), and path traversal prevention on all imports.

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
| **CashVariance** | 🔴 High | Total Cash recorded in Notepad for the day differs from the derived cash in the Cash Register (offset by legal Cash Expenses) by more than `CASH_VARIANCE_TOLERANCE_INR` (default: ₹100.00). | Check cash register for missing deposits. |
| **LatePayment** | 🟡 Medium | A payment is received after the delivery date by more than `LATE_PAYMENT_THRESHOLD_DAYS` (default: 0 days). | Review late payment receipt. |
| **CashUndeposited** | 🔴 High | Total cash marked as received in CRM for the day exceeds the amount recorded in the Cash Register (offset by legal Cash Expenses) by more than `CASH_VARIANCE_TOLERANCE_INR`. *Fires independently of the Notepad — catches pocketing even when the runner also skips the notepad entry.* | Investigate whether the cash was deposited. Cross-check CRM cash payments against register entries for the day. |
| **BackdatedGPayPayment** | 🕵️ Informational | GPay entry in CRM doesn't match MSWIPE on the same day, but aligns exactly with an unlinked MSWIPE surplus on an earlier date. | Verify CRM was updated late. No missing funds. |
| **SuspectedBackdatedCashPayment** | 🕵️ Informational | Cash deficit on run date (Notepad > Register) correlates with an unexplained cash surplus on an earlier date. | Verify notepad was updated late. No missing funds. |
| **SuspectedBackdatedCRMEntry** | 🕵️ Informational | Cash received per CRM on run date, but Register is short. An earlier date's Register has an exact matching surplus. | Verify honest late CRM entry instead of fraud. |
| **PaymentNotConfirmedByNotepad** | 🔵 Low | CRM marks an Online/Card/Paytm payment but notepad has no corresponding entry. | Runner likely omitted entry. Low risk. |

---

## Prerequisites

- **Python 3.9+**
- **pip** (comes with Python)
- **Git** (for cloning)
- **Gemini CLI** — required for OCR parsing of handwritten runner notepad photos (see [Runner Notepad: OCR Parsing Guide](#-runner-notepad-ocr-parsing-guide-sop))
  ```bash
  npm install -g @google/gemini-cli
  gemini auth login
  ```

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

---

## 📋 Runner Notepad: OCR Parsing Guide (SOP)

This section explains how to convert **handwritten runner delivery notepad photos** into structured CSV files that can be imported into the app. This is the required pre-processing step before the Notepad import in the UI wizard.

### Overview

```
📷 Photo of handwritten notepad page
        ↓  scripts/parse_batch.sh
📄 Delivery_notes_<Month>.csv
        ↓  UI Step 5 – Runner Notepad
🗄️ Database (DeliveryEvents + PaymentEvents)
```

### Prerequisites

1. **Gemini CLI** — must be installed and authenticated:
   ```bash
   # Install (if not already)
   npm install -g @google/gemini-cli

   # Authenticate
   gemini auth login
   ```

2. **Register the `/tumbledry:parse` custom command** — the parse script calls `gemini /tumbledry:parse` internally, which is a custom Gemini CLI command defined in `scripts/commands/parse.toml`. You must register it before running the script.

   **What the command does:** Instructs Gemini to act as a structured data extraction assistant — reading handwriting from an image and returning only raw CSV rows (no headers, no commentary). It enforces date cascading so that a date written as a heading above multiple entries is applied to every row in that group.

   **How to register it:** Copy `parse.toml` to your Gemini CLI custom commands directory:

   | OS | Commands directory |
   |----|-------------------|
   | macOS / Linux / Windows (WSL) | `~/.gemini/commands/tumbledry/` |
   | Windows (Native) | `%APPDATA%\gemini\commands\tumbledry\` |

   ```bash
   # macOS / Linux / Windows (WSL)
   mkdir -p ~/.gemini/commands/tumbledry
   cp scripts/commands/parse.toml ~/.gemini/commands/tumbledry/parse.toml

   # Windows (PowerShell)
   New-Item -ItemType Directory -Force "$env:APPDATA\gemini\commands\tumbledry"
   Copy-Item scripts\commands\parse.toml "$env:APPDATA\gemini\commands\tumbledry\parse.toml"
   ```

   Verify registration:
   ```bash
   gemini /tumbledry:parse --help
   ```

3. **The parse script** — located at `scripts/parse_batch.sh`. On macOS/Linux, make it executable once:
   ```bash
   chmod +x scripts/parse_batch.sh
   ```

4. **Image files** — photos of the runner notepad pages in `.jpg`, `.jpeg`, or `.png` format.
   - Take clear, well-lit photos. Avoid shadows or blurry shots.
   - Shoot straight-on (no skew). Each photo should cover one notepad page.

---

### Step 1 — Parse Notepad Photos into CSV

#### Single photo

```bash
./scripts/parse_batch.sh /path/to/notepad_page.jpg
```

#### Batch — entire folder of photos

```bash
./scripts/parse_batch.sh /path/to/notepad_photos/
```

The script will process every `.jpg`, `.jpeg`, and `.png` file in the folder.

**What happens internally:**
- Each image is sent to Gemini AI (`gemini /tumbledry:parse`) which reads the handwriting and returns structured CSV rows.
- Rows are filtered and routed to **month-specific output files** based on the date in column 5.

#### Output files

The script writes CSV files into your **current working directory**:

| File | Contents |
|------|----------|
| `Delivery_notes_January.csv` | All entries dated in January |
| `Delivery_notes_February.csv` | All entries dated in February |
| … | *(one file per month)* |
| `Delivery_notes_Unsorted.csv` | Rows where the date could not be parsed |

> **Tip:** Run the script from a consistent output folder (e.g., `data/notepad_csvs/`) so files don't scatter across the workspace.

#### Sample output

```
Parsing: /photos/notepad_nov_01.jpg
   -> Parsed Date: 01/11/2025 | Routing to: Delivery_notes_November.csv
Parsing: /photos/notepad_nov_02.jpg
   -> Parsed Date: 02/11/2025 | Routing to: Delivery_notes_November.csv
-----------------------------------
Processing complete!
✅ Successfully parsed 2 out of 2 files.
```

---

### Step 2 — Verify the CSV Before Importing

Open the generated CSV and sanity-check a few rows before uploading:

- **Column 5** should contain recognizable dates (`DD/MM/YYYY` format).
- Order numbers, customer names, and amounts should look reasonable.
- Check `Delivery_notes_Unsorted.csv` — if it's non-empty, those rows need manual review and correction before import.

---

### Step 3 — Import into the App (UI Step 5)

1. Launch the Streamlit UI:
   ```bash
   streamlit run src/ui/app.py --server.address localhost
   ```
2. In the **Import Wizard**, complete **Steps 1–4** first (CRM Sales → Orders → Delivery → MSWIPE).
3. On **Step 5 — Runner Notepad**, choose **"Upload File"** mode.
4. Upload the monthly CSV (e.g., `Delivery_notes_November.csv`).
5. Review the preview table, then click **Import**.

> **Note:** The app natively accepts `.csv`, `.xlsx`, and `.xls` — no conversion needed. Use the **Manual Entry** tab in Step 5 as an alternative for small datasets.

---

### Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| `ERROR: Parsing failed or no valid data found` | Blurry/skewed photo, or Gemini CLI not authenticated | Re-shoot the photo clearer; run `gemini auth login` |
| File appears in `Delivery_notes_Unsorted.csv` | Date column (col 5) is missing or in unexpected format | Manually correct the date in the CSV and re-route to the correct monthly file |
| Duplicate rows after re-running | Script **appends** to existing CSVs | Delete or archive old CSV files before re-running the script on the same images |
| `gemini: command not found` | Gemini CLI not installed or not on PATH | Install via `npm install -g @google/gemini-cli` and restart terminal |
| Script won't run (`Permission denied`) | File not executable | Run `chmod +x scripts/parse_batch.sh` |

---

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
