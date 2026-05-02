"""
Expenses Importer.

Imports expense records from Excel/CSV files. Each row represents a single
expense with date, amount, category, description, mode, and vendor.

Uses delete-by-date strategy for idempotent re-imports: all expenses
for the dates present in the file are cleared before inserting new records.
"""

import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter, read_excel_auto, sanitize_raw_data
from src.models.expenses import Expense

logger = logging.getLogger(__name__)


class ExpensesImporter(BaseImporter):

    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, parse_dates=False)
        else:
            # parse_dates=False keeps date columns as raw strings/numbers so
            # we can parse them ourselves with dayfirst=True, avoiding the
            # pandas default of dayfirst=False which mis-parses DD-MM-YYYY as MM-DD-YYYY.
            df = read_excel_auto(file_path, parse_dates=False)
        df = df.where(pd.notnull(df), None)
        return [sanitize_raw_data(row) for row in df.to_dict(orient='records')]

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for row in raw_data:
            # Flexible column name matching
            expense_date = self._parse_date(
                row.get('Date') or row.get('Expense Date') or
                row.get('date') or row.get('expense_date')
            )
            if not expense_date:
                continue

            amount = self._parse_amount(
                row.get('Amount') or row.get('amount') or
                row.get('Expense Amount') or 0
            )
            if amount <= 0:
                continue

            # Category: 'Paid To' in the user's sheet holds the expense category
            # (e.g. "Tea Expenses", "Salary", "petrol Expenses", "Chemical Expenses")
            category = str(
                row.get('Paid To') or row.get('paid_to') or
                row.get('Category') or row.get('category') or
                row.get('Type') or row.get('type') or ''
            ).strip() or 'Misc'

            # Description: 'Narration' in the user's sheet holds freetext details
            description = str(
                row.get('Narration') or row.get('narration') or
                row.get('Description') or row.get('description') or
                row.get('Details') or row.get('details') or
                row.get('Remarks') or row.get('remarks') or ''
            ).strip()

            mode = str(
                row.get('Mode') or row.get('mode') or
                row.get('Payment Mode') or row.get('payment_mode') or 'Cash'
            ).strip()

            # Normalize mode
            mode_lower = mode.lower()
            if mode_lower in ('cash', 'c'):
                mode = 'Cash'
            elif mode_lower in ('online', 'upi', 'gpay', 'google pay', 'neft', 'imps', 'bank'):
                mode = 'Online'
            elif mode_lower in ('card', 'debit', 'credit'):
                mode = 'Card'
            # else keep as-is

            # Vendor: use 'Paid To' as paid_to only when a separate Category exists
            # otherwise paid_to is derived from the category field
            paid_to = category if category != 'Misc' else None

            normalized.append({
                'expense_date': expense_date,
                'amount': amount,
                'category': category,
                'description': description,
                'mode': mode,
                'paid_to': paid_to,
                'raw_data': row,
            })
        return normalized

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out rows with missing date or zero amount."""
        valid = []
        for row in data:
            if not row['expense_date']:
                continue
            if row['amount'] <= 0:
                continue
            valid.append(row)
        return valid

    def save(self, data: List[Dict[str, Any]]) -> None:
        """
        Save with delete-by-date strategy for idempotent re-imports.

        All expenses for the dates present in the import batch are deleted
        before inserting new records, preventing duplicates on re-import.
        """
        # Get dates present in this import batch
        run_dates = set()
        for r in data:
            d = r.get('expense_date')
            if d:
                run_dates.add(d)

        # Clear old expenses FOR THESE DATES so re-importing doesn't duplicate
        if run_dates:
            deleted = self.db.query(Expense).filter(
                Expense.expense_date.in_(run_dates)
            ).delete(synchronize_session=False)
            if deleted:
                logger.info("Cleared %d existing expenses before re-import", deleted)
                self.db.flush()

        for row in data:
            expense = Expense(
                expense_date=row['expense_date'],
                amount=row['amount'],
                category=row['category'],
                description=row['description'],
                mode=row['mode'],
                paid_to=row['paid_to'],
                raw_data=row['raw_data'],
            )
            self.db.add(expense)

    def _parse_date(self, date_str: Any) -> Optional[Any]:
        import re
        from datetime import date as _date
        if date_str is None or (isinstance(date_str, float) and pd.isna(date_str)) or str(date_str).strip() == '':
            return None
        # Excel stores dates as serial integers (days since 1899-12-30)
        if isinstance(date_str, (int, float)):
            try:
                return (pd.Timestamp('1899-12-30') + pd.Timedelta(days=int(date_str))).date()
            except Exception:
                return None
        s = str(date_str).strip()
        # ISO format: YYYY-MM-DD (with optional time) — parse directly, no ambiguity
        iso_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
        if iso_match:
            try:
                return _date(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)))
            except Exception:
                pass
        # Non-ISO (DD-MM-YYYY, DD/MM/YYYY, etc.) — use dayfirst=True
        try:
            return parse(s, dayfirst=True).date()
        except Exception:
            return None


    def _parse_amount(self, amount: Any) -> float:
        if amount is None or (isinstance(amount, float) and pd.isna(amount)) or str(amount).strip() == '':
            return 0.0
        try:
            return float(str(amount).replace(',', '').replace('₹', '').strip())
        except Exception:
            return 0.0
