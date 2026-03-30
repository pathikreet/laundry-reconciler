import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import date, timedelta
from sqlalchemy.orm import Session
from src.importers.base import BaseImporter, read_excel_auto
import os
from src.models.cash_register import CashRegisterEntry
from src.models.reconciliation import ReconciliationRun
import logging

logger = logging.getLogger(__name__)

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

        # We need to flatten this grid into a list of daily entries.
        # Assuming index/first column is Day (1-31).
        # And columns are Month names.

        data = []
        df = df.where(pd.notnull(df), None)

        # Month mapping
        month_map_names = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
            'January': 1, 'February': 2, 'March': 3, 'April': 4, 'June': 6,
            'July': 7, 'August': 8, 'September': 9, 'October': 10, 'November': 11, 'December': 12
        }

        # 1. Identify Month Columns (O(Cols))
        col_month_map = {}
        for col in df.columns:
            month_str = str(col).strip()
            for k, v in month_map_names.items():
                if k.lower() in month_str.lower():
                    col_month_map[col] = v
                    break

        # 2. Iterate Rows (O(Rows))
        # Example Input Row: [1, 500, 600, ...] where 1 is Day, 500 is Jan Closing, 600 is Feb Closing
        for idx, row in df.iterrows():
            # Skip if day column is missing or invalid
            try:
                day_val = row.iloc[0]
                day = int(float(str(day_val))) # handle '1.0'
                if day < 1 or day > 31:
                    continue
            except:
                continue

            # Extract data for each identified month column
            for col, month in col_month_map.items():
                closing_balance = self._parse_amount(row[col])

                # Check if date is valid
                try:
                    entry_date = date(year, month, day)
                    data.append({
                        'entry_date': entry_date,
                        'closing_balance': closing_balance,
                        'raw_data': {'day': day, 'month': month, 'year': year, 'val': row[col]}
                    })
                except ValueError:
                    # Invalid date (e.g., Feb 30)
                    continue

        return data

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # The raw_data is already somewhat normalized in import_data because of the grid structure.
        # But we need to calculate `prior_closing_balance` and `derived_cash_from_orders`.

        # To do this efficiently, we should sort by date.
        sorted_data = sorted(raw_data, key=lambda x: x['entry_date'])

        # Create a lookup for quick access
        date_map = {d['entry_date']: d for d in sorted_data}

        normalized_data = []
        # Note: This loop calculates derived values like 'derived_cash_from_orders'.
        # While the Excel sheet is the source of truth for the *closing balance*,
        # the database acts as the persistence store for the *reconciliation application*,
        # allowing us to efficiently query historical balances (via the 5-day lookback)
        # without re-parsing the entire Excel history every time a single day is reconciled.
        for row in sorted_data:
            entry_date = row['entry_date']
            closing_balance = row['closing_balance']

            # Find prior closing balance
            prior_balance = 0.0
            found_prior = False

            # Look back up to 5 days
            for i in range(1, 6):
                prev_date = entry_date - timedelta(days=i)

                if prev_date in date_map:
                    prior_val = date_map[prev_date]['closing_balance']
                    if prior_val > 0: # Assuming 0 means missing/closed
                        prior_balance = prior_val
                        found_prior = True
                        break
                else:
                    # Check DB
                    prev_entry = self.db.query(CashRegisterEntry).filter_by(entry_date=prev_date).first()
                    if prev_entry and prev_entry.closing_balance and prev_entry.closing_balance > 0:
                        prior_balance = float(prev_entry.closing_balance)
                        found_prior = True
                        break

            # If not found, prior_balance is 0 (or we should mark as partial validation)

            expenses = 0.0 # Default expenses to 0

            derived_cash = closing_balance - prior_balance + expenses

            row['prior_closing_balance'] = prior_balance
            row['expenses_deposits'] = expenses
            row['derived_cash_from_orders'] = derived_cash
            row['validation_status'] = 'valid' if found_prior else 'partial'

            normalized_data.append(row)

        return normalized_data

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return data

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
                entry.derived_cash_from_orders = row['derived_cash_from_orders']
                entry.validation_status = row['validation_status']

        self.db.commit()

    def _parse_amount(self, amount: Any) -> float:
        if amount is None or pd.isna(amount) or str(amount).strip() == '':
            return 0.0
        try:
            return float(str(amount).replace(',', '').replace('₹', '').strip())
        except:
            return 0.0
