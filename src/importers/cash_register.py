import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
from src.importers.base import BaseImporter, read_excel_auto
import os
from src.models.cash_register import CashRegisterEntry
from src.models.bank_deposit import BankDeposit
from src.models.expenses import Expense
from src.models.reconciliation import ReconciliationRun
import logging

logger = logging.getLogger(__name__)

# ── Month name → number mapping ──────────────────────────────
MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'feburary': 2,  # common misspelling
    'march': 3, 'april': 4, 'june': 6, 'july': 7,
    'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12,
}


class CashRegisterImporter(BaseImporter):
    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        # kwargs should contain 'year' and/or 'sheet_name'
        explicit_year = kwargs.get('year')
        sheet_name = kwargs.get('sheet_name', str(explicit_year or date.today().year))

        # Derive year from sheet_name if it looks like a year (e.g. "2025")
        if isinstance(sheet_name, str) and sheet_name.isdigit() and len(sheet_name) == 4:
            year = int(sheet_name)
        else:
            year = explicit_year or date.today().year

        try:
            # Check if sheet exists, if not try to infer or use first
            xls_engine = 'xlrd' if os.path.splitext(file_path)[1].lower() == '.xls' else None
            xl = pd.ExcelFile(file_path, engine=xls_engine)
            if sheet_name not in xl.sheet_names:
                # Fallback to first sheet if only one exists or year matches
                if str(year) in xl.sheet_names:
                    sheet_name = str(year)
                else:
                    sheet_name = xl.sheet_names[0]

            logger.info("Importing Cash Register: sheet='%s', year=%d", sheet_name, year)
            df = read_excel_auto(file_path, sheet_name=sheet_name)
        except Exception as e:
            print(f"Error reading Excel file: {e}")
            return []

        # ── Parse the daily closing balance grid ───────────────
        data = []
        df = df.where(pd.notnull(df), None)

        # Identify Month Columns
        col_month_map = {}
        for col in df.columns:
            month_str = str(col).strip()
            for k, v in MONTH_MAP.items():
                if k.lower() in month_str.lower():
                    col_month_map[col] = v
                    break

        # Iterate Rows
        for idx, row in df.iterrows():
            try:
                day_val = row.iloc[0]
                day = int(float(str(day_val)))  # handle '1.0'
                if day < 1 or day > 31:
                    continue
            except Exception:
                continue

            for col, month in col_month_map.items():
                closing_balance = self._parse_amount(row[col])
                try:
                    entry_date = date(year, month, day)
                    data.append({
                        'entry_date': entry_date,
                        'closing_balance': closing_balance,
                        'raw_data': {'day': day, 'month': month, 'year': year, 'val': row[col]}
                    })
                except ValueError:
                    continue

        # ── Parse the Bank Deposits table ──────────────────────
        bank_deposits = self._parse_bank_deposits(file_path, sheet_name, year)
        # Stash on self so normalize() and save() can access them
        self._bank_deposits = bank_deposits
        self._import_year = year

        logger.info(
            "Cash register: %d daily entries, %d bank deposits parsed",
            len(data), len(bank_deposits)
        )
        return data

    # ── Bank Deposits Parser ──────────────────────────────────

    def _parse_bank_deposits(self, file_path: str, sheet_name: str,
                              year: int) -> List[Dict[str, Any]]:
        """Parse the 'Bank Deposits' table from the same sheet.

        The table has a header row containing:
            Month | Day Of Month | Deposit Amount
        followed by data rows. It is located to the right of the daily
        closing balance grid.
        """
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        deposits = []

        # Find the header row that contains BOTH "Day Of Month" AND "Deposit Amount".
        # We can't just look for "Day Of Month" alone because the daily closing
        # balance grid also has a "Day Of Month" column header (at row 0).
        header_row = None
        month_col = day_col = amt_col = None

        for idx, row in df.iterrows():
            row_cells = {
                c: str(df.iloc[idx, c]).strip().lower()
                for c in range(len(df.columns))
                if pd.notna(df.iloc[idx, c])
            }
            has_day = any('day of month' in v for v in row_cells.values())
            has_deposit = any('deposit' in v and 'amount' in v for v in row_cells.values())

            if has_day and has_deposit:
                header_row = idx
                for c, val in row_cells.items():
                    if val == 'month':
                        month_col = c
                    elif 'day of month' in val:
                        day_col = c
                    elif 'deposit' in val and 'amount' in val:
                        amt_col = c
                break

        if header_row is None:
            logger.info("No 'Bank Deposits' table found in sheet '%s'", sheet_name)
            return []

        if month_col is None or day_col is None or amt_col is None:
            logger.warning(
                "Bank Deposits header incomplete: month=%s, day=%s, amt=%s",
                month_col, day_col, amt_col
            )
            return []

        # Read data rows after the header
        for i in range(header_row + 1, len(df)):
            month_val = df.iloc[i, month_col] if pd.notna(df.iloc[i, month_col]) else None
            day_val = df.iloc[i, day_col] if pd.notna(df.iloc[i, day_col]) else None
            amt_val = df.iloc[i, amt_col] if pd.notna(df.iloc[i, amt_col]) else None

            if month_val is None or day_val is None or amt_val is None:
                continue

            month_str = str(month_val).strip()
            if not month_str or month_str.lower() in ('nan', 'none'):
                continue

            # Resolve month number
            month_num = MONTH_MAP.get(month_str.lower())
            if month_num is None:
                logger.warning("Unknown month '%s' in bank deposits", month_str)
                continue

            try:
                day = int(float(str(day_val)))
                amt = abs(float(str(amt_val).replace(',', '')))
            except (ValueError, TypeError):
                continue

            try:
                deposit_date = date(year, month_num, day)
            except ValueError:
                continue

            deposits.append({
                'deposit_date': deposit_date,
                'amount': amt,
                'month_label': month_str,
                'raw_data': {
                    'month': month_str, 'day': day,
                    'amount': amt, 'year': year
                },
            })
            logger.info(
                "Bank deposit: %s Rs %.0f (%s %d)",
                deposit_date, amt, month_str, day
            )

        return deposits

    # ── Normalize ─────────────────────────────────────────────

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate derived values from raw closing balances.

        The key derivation is ``derived_cash_from_orders``:

            derived_cash = closing - prior + expenses + bank_deposits

        This represents the **true cash collected from orders** for the day:
        we start with the net register change (closing − prior) and add back
        known outflows (expenses paid from register, cash deposited to bank)
        so they don't appear as "missing" cash.

        **Zero-closing days** (Sundays / holidays where the shop is closed)
        are handled specially: ``derived_cash_from_orders = 0`` because no
        register activity occurred.
        """
        sorted_data = sorted(raw_data, key=lambda x: x['entry_date'])

        # Create a lookup for quick access
        date_map = {d['entry_date']: d for d in sorted_data}

        # Build bank-deposit lookup by date
        deposit_map: Dict[date, float] = {}
        for dep in getattr(self, '_bank_deposits', []):
            d = dep['deposit_date']
            deposit_map[d] = deposit_map.get(d, 0.0) + dep['amount']

        normalized_data = []
        for row in sorted_data:
            entry_date = row['entry_date']
            closing_balance = row['closing_balance']

            # ── Zero-closing day (shop closed / Sunday / holiday) ──
            if closing_balance == 0 or closing_balance is None:
                row['prior_closing_balance'] = 0.0
                row['expenses_deposits'] = 0.0
                row['derived_cash_from_orders'] = 0.0
                row['validation_status'] = 'closed'
                normalized_data.append(row)
                continue

            # ── Find prior closing balance ──
            prior_balance = 0.0
            found_prior = False

            for i in range(1, 6):
                prev_date = entry_date - timedelta(days=i)

                if prev_date in date_map:
                    prior_val = date_map[prev_date]['closing_balance']
                    if prior_val > 0:
                        prior_balance = prior_val
                        found_prior = True
                        break
                else:
                    prev_entry = self.db.query(CashRegisterEntry).filter_by(
                        entry_date=prev_date
                    ).first()
                    if prev_entry and prev_entry.closing_balance and prev_entry.closing_balance > 0:
                        prior_balance = float(prev_entry.closing_balance)
                        found_prior = True
                        break

            # ── Look up outflows for this date ──
            # Bank deposits (from the same Excel file)
            day_bank_deposit = deposit_map.get(entry_date, 0.0)

            # Cash expenses (from the Expenses table in DB)
            day_expenses = float(
                self.db.query(sa_func.sum(Expense.amount)).filter(
                    Expense.expense_date == entry_date,
                    Expense.mode == 'Cash',
                ).scalar() or 0.0
            )

            # ── Compute derived cash from orders ──
            # closing = prior + orders_cash_in - expenses_out - bank_deposit
            # ∴ orders_cash_in = closing - prior + expenses_out + bank_deposit
            outflows = day_expenses + day_bank_deposit
            derived_cash = closing_balance - prior_balance + outflows

            row['prior_closing_balance'] = prior_balance
            row['expenses_deposits'] = outflows
            row['derived_cash_from_orders'] = derived_cash
            row['validation_status'] = 'valid' if found_prior else 'partial'

            normalized_data.append(row)

        return normalized_data

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        today = date.today()
        valid = []
        skipped = 0
        for row in data:
            entry_date = row.get('entry_date')
            closing = row.get('closing_balance', 0) or 0
            # Skip future-dated rows that have zero closing balance.
            # These are template/placeholder rows in the annual register spreadsheet
            # that haven't been filled in yet.
            if entry_date and entry_date > today and closing == 0:
                skipped += 1
                continue
            valid.append(row)
        if skipped:
            logger.info("Skipped %d future-dated zero-balance cash register rows", skipped)
        return valid

    def save(self, data: List[Dict[str, Any]]) -> None:
        for row in data:
            entry = self.db.query(CashRegisterEntry).filter_by(entry_date=row['entry_date']).first()
            if not entry:
                entry = CashRegisterEntry(
                    entry_date=row['entry_date'],
                    closing_balance=row['closing_balance'],
                    prior_closing_balance=row['prior_closing_balance'],
                    expenses_deposits=row['expenses_deposits'],
                    derived_cash_from_orders=row['derived_cash_from_orders'],
                    validation_status=row['validation_status'],
                    raw_data=row['raw_data']
                )
                self.db.add(entry)
            else:
                entry.closing_balance = row['closing_balance']
                entry.prior_closing_balance = row['prior_closing_balance']
                entry.expenses_deposits = row['expenses_deposits']
                entry.derived_cash_from_orders = row['derived_cash_from_orders']
                entry.validation_status = row['validation_status']

        # ── Save bank deposits ─────────────────────────────────
        year = getattr(self, '_import_year', None)
        deposits = getattr(self, '_bank_deposits', [])
        if deposits and year:
            # Clear existing deposits for this year range to avoid duplicates
            year_start = date(year, 1, 1)
            year_end = date(year, 12, 31)
            self.db.query(BankDeposit).filter(
                BankDeposit.deposit_date >= year_start,
                BankDeposit.deposit_date <= year_end,
            ).delete()

            for dep in deposits:
                self.db.add(BankDeposit(
                    deposit_date=dep['deposit_date'],
                    amount=dep['amount'],
                    month_label=dep['month_label'],
                    raw_data=dep['raw_data'],
                ))
            logger.info("Saved %d bank deposits for year %d", len(deposits), year)

        self.db.commit()

    def _parse_amount(self, amount: Any) -> float:
        if amount is None or pd.isna(amount) or str(amount).strip() == '':
            return 0.0
        try:
            return float(str(amount).replace(',', '').replace('₹', '').strip())
        except Exception:
            return 0.0
