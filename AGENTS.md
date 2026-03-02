# AGENTS.md — Laundry Reconciler

> Reconciles laundry biz data: CRM (Sales+Orders+Delivery) + MSWIPE + Cash Register + Notepad → matched orders, exceptions, Excel reports.

## Stack
Python 3.9+ · SQLite/SQLAlchemy 2.x · pydantic-settings · pandas · rapidfuzz · Streamlit · xlsxwriter · pytest

## Tree
```
src/
├── cli.py              # CLI (argparse): init-db|import-crm|import-crm-orders|import-crm-delivery|import-mswipe|import-notepad|import-cash|reconcile
├── exceptions.py       # Error hierarchy: LaundryReconcilerError → Import/File/DB/Recon/Export/MatchError
├── config/settings.py  # pydantic-settings (BaseSettings, .env support), tolerances, payment_mode_mapping
├── db/init_db.py       # DB init w/ path sanitization
├── exporters/excel_exporter.py  # 6-sheet Excel (Orders|Exceptions|Notepad|MSWIPE|Summary|Audit)
├── importers/
│   ├── base.py         # BaseImporter: import→normalize→validate→save (tx rollback on fail)
│   ├── crm.py          # CRM Sales: sort-by-date, group-by-order, 1 Order + N PaymentEvents
│   ├── crm_delivery.py # CRM Delivery: DeliveryEvent linked to Order by order_number
│   ├── crm_orders.py   # CRM Orders: authoritative Net Amount, enriches existing Orders
│   ├── mswipe.py|cash_register.py|notepad.py
├── models/             # ORM: Order|PaymentEvent|DeliveryEvent|ReconciliationRun|OrderException|AuditLog|CashRegisterEntry|ColumnMapping|ToleranceConfig
├── repositories/base.py  # BaseRepository[T]: CRUD + cascade-safe delete
├── services/
│   ├── matching.py     # Batch matching (100/batch), exact→fuzzy, confidence+explanations
│   └── reconciliation.py  # Rules: delivery status|credit policy|late payments|gpay totals|cash variance
└── ui/
    ├── app.py          # Streamlit: guided import wizard (6 steps), manual notepad entry, recon, results
    └── styles.css      # Custom CSS: step cards, progress bar, severity badges
tests/
├── conftest.py         # In-memory SQLite + transactional rollback fixtures
└── 10 test files       # 39 tests: CRUD, importers, matching, recon, exporter, error paths
```

## Data Flow
```
CRM Sales Report ─┐
CRM Orders Report ─┤──→ Orders + PaymentEvents
CRM Delivery Report┤──→ DeliveryEvents
MSWIPE ────────────┤──→ PaymentEvents
Runner Notepad ────┤──→ DeliveryEvents + PaymentEvents (file upload OR manual form)
Cash Register ─────┘──→ CashRegisterEntries

All ──→ MatchingService ──→ ReconciliationService ──→ OrderExceptions ──→ ExcelExporter
```

## Import Pipeline
`BaseImporter.run()` → `import_data→normalize→validate→save` → `db.commit()` or `db.rollback()`. Returns `{total, imported, errors}`.

**CRM Sales (`crm.py`):** Sorts by payment_date → groups by order_number → aggregates: 1 Order + N PaymentEvents per group. Derives `order_amount = ΣPayment + ΣAdjustments + final Balance`.

**CRM Orders (`crm_orders.py`):** Updates existing Orders with authoritative `Net Amount`. Creates new Orders for entries not in Sales. Stores Due Date, Pcs, Package in `raw_data`.

**CRM Delivery (`crm_delivery.py`):** Creates DeliveryEvents linked to Orders by order_number. Enables late-payment detection.

**Recommended import order:** Sales → Orders → Delivery → MSWIPE → Notepad → Cash Register.

## Recon Rules
`ReconciliationService.run_reconciliation(date)` → `_initialize_run` → `_check_order_rules` (delivery status, credit policy) → `_check_late_payments` (payment after delivery) → `_check_day_rules` (gpay totals, cash variance) → `OrderException` records w/ severity.

**Late Payments:** Configurable `late_payment_threshold_days` (default 0). Flags payments made ≥N days after CRM delivery date.

## Config
`src/config/settings.py` — inherits from `pydantic_settings.BaseSettings` (.env + env vars):
- `amount_tolerance=₹2` · `date_window_days=3` · `fuzzy_name_threshold=0.82`
- `credit_tolerance=₹1` · `cash_variance_tolerance=₹100` · `gpay_tolerance=₹10`
- `late_payment_threshold_days=0`
- `payment_mode_mapping`: cash|gpay|google pay|upi|paytm|package|online|card

## Commands
```bash
python -m venv venv && .\venv\Scripts\activate && pip install -r requirements.txt
python -m src.cli init-db
python -m src.cli import-crm <sales.xlsx>
python -m src.cli import-crm-orders <orders.xlsx>
python -m src.cli import-crm-delivery <delivery.xlsx>
python -m src.cli import-mswipe|import-notepad|import-cash <file>
python -m src.cli reconcile 2025-11-15 [--export]
streamlit run src/ui/app.py --server.address localhost
python -m pytest tests/ -v
```
> Always `python -m src.cli`, never `python src/cli.py`.

## UI
Streamlit guided wizard with 6 steps. Sales required first (gates steps 2-6). Each step: upload → preview → import → summary. **Notepad** has dual mode: file upload OR manual entry form with "Add Order Details" button. Progress bar + status badges.

## Gaps
- No auth (localhost mitigates) · No OCR (PRD §2.2) · No configurable severity in UI · Integration test coverage thin

## Extend
New source? → `src/importers/new.py(BaseImporter)` + CLI subcommand + UI step + `ALLOWED_EXTENSIONS` entry + test file.
