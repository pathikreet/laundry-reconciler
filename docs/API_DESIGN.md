# API Design — Laundry Reconciler MVP

## 1. Module Structure

```
laundry_reconciler/
├── services/
│   ├── import_service.py       # File ingestion and column mapping
│   ├── reconciliation_service.py  # Orchestration
│   ├── export_service.py       # Excel workbook generation
│   └── config_service.py       # Tolerances and settings
├── engines/
│   ├── normalizer.py           # Data normalization
│   ├── matcher.py              # Order-payment matching
│   └── rules.py                # Business rule execution
├── repositories/
│   ├── order_repo.py
│   ├── payment_repo.py
│   ├── delivery_repo.py
│   ├── exception_repo.py
│   └── audit_repo.py
├── models/
│   ├── entities.py             # Dataclasses for domain objects
│   └── enums.py                # PaymentMode, Severity, etc.
└── utils/
    ├── date_parser.py
    └── amount_parser.py
```

---

## 2. Core Interfaces

### 2.1 Import Service

```python
# services/import_service.py

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from models.entities import ImportResult, ColumnMapping

class ImportService:
    """Handles file ingestion, column mapping, and data persistence."""
    
    def import_crm_export(
        self,
        file_path: Path,
        mapping: ColumnMapping,
        reconciliation_run_id: int
    ) -> ImportResult:
        """
        Import CRM sales export file.
        
        Args:
            file_path: Path to Excel/CSV file
            mapping: Column name mapping configuration
            reconciliation_run_id: Associated reconciliation run
            
        Returns:
            ImportResult with counts and validation errors
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValidationError: If required columns are missing
        """
        ...
    
    def import_mswipe_transactions(
        self,
        file_path: Path,
        mapping: ColumnMapping,
        reconciliation_run_id: int
    ) -> ImportResult:
        """Import MSWIPE payment transactions CSV."""
        ...
    
    def import_cash_register(
        self,
        file_path: Path,
        year_sheet: str,
        month_column_mapping: dict[str, str],  # {"January": "B", ...}
        target_date: date,
        reconciliation_run_id: int
    ) -> ImportResult:
        """
        Import cash register closing balance for a date.
        
        Handles:
        - Grid layout parsing (rows = days, columns = months)
        - Cross-month lookups for C_(d-1)
        - Up to 5-day lookback for missing values
        """
        ...
    
    def save_notepad_entries(
        self,
        entries: list[NotepadEntry],
        reconciliation_run_id: int
    ) -> ImportResult:
        """Save manually entered notepad lines."""
        ...
    
    def get_column_suggestions(
        self,
        file_path: Path,
        source_type: str
    ) -> dict[str, list[str]]:
        """
        Suggest column mappings based on header patterns.
        
        Returns:
            Dict mapping required fields to candidate column names
        """
        ...
    
    def save_mapping_profile(
        self,
        name: str,
        source_type: str,
        mapping: ColumnMapping,
        is_default: bool = False
    ) -> int:
        """Save column mapping profile for reuse."""
        ...

@dataclass
class ImportResult:
    """Result of an import operation."""
    success: bool
    rows_imported: int
    rows_failed: int
    validation_errors: list[ValidationError]
    import_run_id: int

@dataclass
class ValidationError:
    """Import validation error details."""
    row_number: int
    column: str
    message: str
    value: Optional[str]
```

---

### 2.2 Reconciliation Service

```python
# services/reconciliation_service.py

from dataclasses import dataclass
from datetime import date
from typing import Optional
from models.entities import ReconciliationRun, ReconciliationResult

class ReconciliationService:
    """Orchestrates the complete reconciliation process for a date."""
    
    def create_run(self, run_date: date) -> ReconciliationRun:
        """
        Create a new reconciliation run for the specified date.
        
        Returns:
            ReconciliationRun with pending status
        """
        ...
    
    def execute_reconciliation(
        self,
        run_id: int,
        config_overrides: Optional[dict] = None
    ) -> ReconciliationResult:
        """
        Execute full reconciliation for a run.
        
        Steps:
        1. Load all imported data for run date
        2. Execute matching engine
        3. Apply business rules
        4. Generate exceptions
        5. Compute summary statistics
        6. Update run status
        
        Args:
            run_id: Reconciliation run ID
            config_overrides: Optional tolerance overrides
            
        Returns:
            ReconciliationResult with matches, exceptions, summary
        """
        ...
    
    def get_order_ledger(
        self,
        order_id: int
    ) -> OrderLedger:
        """
        Get order mini-ledger with payment history.
        
        Returns:
            OrderLedger with:
            - order_amount
            - total_paid_to_date
            - advance_paid_before_delivery
            - paid_on_delivery_day
            - balance_due_at_delivery
        """
        ...
    
    def resolve_exception(
        self,
        exception_id: int,
        resolution: str,  # 'resolved' | 'false_positive'
        note: Optional[str] = None
    ) -> None:
        """Mark an exception as resolved with optional note."""
        ...
    
    def link_notepad_to_order(
        self,
        delivery_event_id: int,
        order_id: int
    ) -> None:
        """Manually link a notepad entry to an order."""
        ...

@dataclass
class ReconciliationResult:
    """Result of reconciliation execution."""
    run_id: int
    status: str
    matched_orders: int
    unmatched_notepad: int
    unmatched_mswipe: int
    exceptions: list[Exception]
    summary: DaySummary

@dataclass
class OrderLedger:
    """Order payment mini-ledger."""
    order_id: int
    order_number: str
    order_amount: Decimal
    total_paid_to_date: Decimal
    advance_paid_before_delivery: Decimal
    paid_on_delivery_day: Decimal
    balance_due_at_delivery: Decimal
    payment_events: list[PaymentEvent]
```

---

### 2.3 Matching Engine

```python
# engines/matcher.py

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

class MatchingEngine:
    """Matches orders with payments and deliveries."""
    
    def match_orders_to_payments(
        self,
        orders: list[Order],
        payments: list[PaymentEvent],
        config: MatchingConfig
    ) -> list[MatchResult]:
        """
        Match orders to payment events.
        
        Strategy (priority order):
        1. Exact match by order_number
        2. Fuzzy match by customer_name + amount + date proximity
        
        Returns:
            List of MatchResult with confidence scores
        """
        ...
    
    def match_orders_to_deliveries(
        self,
        orders: list[Order],
        deliveries: list[DeliveryEvent],
        config: MatchingConfig
    ) -> list[MatchResult]:
        """Match orders to delivery events (notepad entries)."""
        ...
    
    def match_mswipe_to_crm_payments(
        self,
        mswipe_payments: list[PaymentEvent],
        crm_payments: list[PaymentEvent],
        config: MatchingConfig
    ) -> list[MSWIPEMatchResult]:
        """
        Link MSWIPE transactions to CRM GPay payments.
        
        Match criteria:
        - Amount within tolerance
        - Time within window (180 min default)
        - Mode is GPay/UPI
        
        Returns:
            MSWIPEMatchResult with linked/unlinked transactions
        """
        ...

@dataclass
class MatchingConfig:
    """Matching tolerances and thresholds."""
    amount_tolerance_inr: Decimal = Decimal('2')
    fuzzy_name_min_score: float = 0.82
    fuzzy_date_proximity_days: int = 3
    mswipe_time_window_minutes: int = 180
    require_manual_review_below: float = 0.7

@dataclass
class MatchResult:
    """Result of a single match attempt."""
    source_id: int
    source_type: str  # 'payment' | 'delivery'
    matched_order_id: Optional[int]
    confidence_score: float
    match_evidence: dict  # {"field": "value", ...}
    requires_review: bool
```

---

### 2.4 Rule Engine

```python
# engines/rules.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

class ReconciliationRule(ABC):
    """Base class for business rules."""
    
    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier."""
        ...
    
    @property
    @abstractmethod
    def priority(self) -> int:
        """Execution priority (lower = first)."""
        ...
    
    @abstractmethod
    def evaluate(
        self,
        context: RuleContext
    ) -> list[ExceptionResult]:
        """Evaluate rule and return any exceptions."""
        ...

class RuleEngine:
    """Executes business rules in priority order."""
    
    def __init__(self, rules: list[ReconciliationRule]):
        self._rules = sorted(rules, key=lambda r: r.priority)
    
    def execute_rules(
        self,
        context: RuleContext
    ) -> list[ExceptionResult]:
        """
        Execute all rules in priority order.
        
        Returns:
            Combined list of exceptions from all rules
        """
        ...

@dataclass
class RuleContext:
    """Context passed to rules for evaluation."""
    run_date: date
    orders: list[Order]
    payment_events: list[PaymentEvent]
    delivery_events: list[DeliveryEvent]
    matches: list[MatchResult]
    cash_register: Optional[CashRegisterEntry]
    config: ToleranceConfig

@dataclass
class ExceptionResult:
    """Exception generated by a rule."""
    order_id: Optional[int]
    severity: str  # 'high' | 'medium' | 'low'
    exception_type: str
    reason_tags: list[str]
    evidence: dict
    suggested_action: str
```

---

### 2.5 Export Service

```python
# services/export_service.py

from pathlib import Path
from dataclasses import dataclass

class ExportService:
    """Generates Excel workbook exports."""
    
    def export_reconciliation(
        self,
        run_id: int,
        output_path: Path
    ) -> ExportResult:
        """
        Export reconciliation results as Excel workbook.
        
        Sheets (per PRD §4.2):
        1. Reconciled_Orders
        2. Exceptions
        3. Unmatched_Notepad
        4. Unmatched_MSWIPE
        5. Daily_Summary
        6. Audit_Log
        
        Returns:
            ExportResult with file path and sheet row counts
        """
        ...
    
    def _write_reconciled_orders(
        self,
        worksheet,
        run_id: int
    ) -> int:
        """Write reconciled orders sheet. Returns row count."""
        ...
    
    def _write_exceptions(
        self,
        worksheet,
        run_id: int
    ) -> int:
        """Write exceptions sheet with reason column."""
        ...
    
    def _write_daily_summary(
        self,
        worksheet,
        run_id: int
    ) -> None:
        """
        Write summary with:
        - Totals by payment mode (CRM vs Notepad vs MSWIPE)
        - Cash variance signal vs expected
        """
        ...

@dataclass
class ExportResult:
    """Result of export operation."""
    success: bool
    file_path: Path
    sheet_row_counts: dict[str, int]
    error: Optional[str]
```

---

### 2.6 Config Service

```python
# services/config_service.py

from decimal import Decimal
from dataclasses import dataclass

class ConfigService:
    """Manages application configuration and tolerances."""
    
    def get_tolerance(self, key: str) -> str:
        """Get tolerance value by key."""
        ...
    
    def set_tolerance(self, key: str, value: str) -> None:
        """Set tolerance value."""
        ...
    
    def get_all_tolerances(self) -> ToleranceConfig:
        """Get all tolerances as config object."""
        ...
    
    def reset_to_defaults(self) -> None:
        """Reset all tolerances to PRD defaults."""
        ...

@dataclass
class ToleranceConfig:
    """All configurable tolerances."""
    amount_match_tolerance_inr: Decimal = Decimal('2')
    daily_total_tolerance_inr: Decimal = Decimal('10')
    daily_total_tolerance_percent: Decimal = Decimal('0.5')
    mswipe_time_match_window_minutes: int = 180
    fuzzy_name_min_score: float = 0.82
    fuzzy_date_proximity_days: int = 3
    cash_variance_tolerance_inr: Decimal = Decimal('100')
    cash_variance_tolerance_percent: Decimal = Decimal('1.0')
    credit_tolerance_inr: Decimal = Decimal('1')
```

---

## 3. Error Handling

### Error Hierarchy

```python
# models/errors.py

class LaundryReconcilerError(Exception):
    """Base exception for all application errors."""
    pass

class ImportError(LaundryReconcilerError):
    """Errors during file import."""
    pass

class ValidationError(ImportError):
    """Data validation failures."""
    def __init__(self, field: str, message: str, value: any = None):
        self.field = field
        self.message = message
        self.value = value

class ColumnMappingError(ImportError):
    """Required column not mapped."""
    def __init__(self, missing_columns: list[str]):
        self.missing_columns = missing_columns

class FileFormatError(ImportError):
    """Unsupported or corrupt file format."""
    pass

class ReconciliationError(LaundryReconcilerError):
    """Errors during reconciliation."""
    pass

class ConfigError(LaundryReconcilerError):
    """Configuration errors."""
    pass
```

### Error Handling Contract

| Layer | Error Behavior |
|-------|---------------|
| **Repository** | Wrap DB errors, add context |
| **Service** | Log errors, return result objects with error details |
| **Engine** | Raise specific exceptions with evidence |
| **UI** | Display user-friendly messages from error.message |

---

## 4. Repository Interfaces

```python
# repositories/base_repo.py

from typing import TypeVar, Generic, Optional

T = TypeVar('T')

class BaseRepository(Generic[T]):
    """Base repository with common operations."""
    
    def get_by_id(self, id: int) -> Optional[T]:
        ...
    
    def get_all(self) -> list[T]:
        ...
    
    def save(self, entity: T) -> int:
        """Save entity, return ID."""
        ...
    
    def update(self, entity: T) -> None:
        ...
    
    def delete(self, id: int) -> None:
        ...

# repositories/order_repo.py

class OrderRepository(BaseRepository[Order]):
    """Order-specific queries."""
    
    def find_by_order_number(self, order_number: str) -> Optional[Order]:
        ...
    
    def find_by_date_range(
        self, 
        start_date: date, 
        end_date: date
    ) -> list[Order]:
        ...
    
    def find_by_customer_name(
        self,
        name: str,
        fuzzy: bool = False
    ) -> list[Order]:
        ...
    
    def get_with_payment_summary(
        self,
        order_id: int
    ) -> OrderWithPayments:
        """Get order with aggregated payment info."""
        ...
```

---

## 5. Normalizer Utilities

```python
# engines/normalizer.py

from decimal import Decimal
from datetime import date
from typing import Optional

class Normalizer:
    """Data normalization utilities."""
    
    def normalize_customer_name(self, name: str) -> str:
        """
        Normalize customer name:
        - Trim whitespace
        - Title case
        - Remove extra spaces
        """
        ...
    
    def parse_date(self, value: any) -> Optional[date]:
        """
        Parse date from various formats:
        - DD-MMM-YYYY (01-Nov-2025)
        - DD/MM/YYYY
        - YYYY-MM-DD
        - Excel serial numbers
        """
        ...
    
    def parse_amount(self, value: any) -> Decimal:
        """
        Parse amount:
        - Remove currency symbols (₹, Rs, INR)
        - Handle commas (1,000.00)
        - Handle negative values
        """
        ...
    
    def normalize_payment_mode(
        self,
        mode: str,
        custom_mapping: Optional[dict] = None
    ) -> str:
        """
        Normalize payment mode to standard values:
        - Cash, GPay, Paytm, Package, Other
        
        Handles variations:
        - 'Google Pay' → 'GPay'
        - 'UPI' → 'GPay'
        - 'GOOGLEPAY' → 'GPay'
        """
        ...
    
    def classify_mswipe_as_gpay(
        self,
        interchange: str,
        card_type: str,
        payee_vpa: str
    ) -> bool:
        """
        Determine if MSWIPE transaction is UPI/GPay.
        Per PRD: All MSWIPE transactions shown as GPay.
        """
        return True  # Per PRD requirement
```
