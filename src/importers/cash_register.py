"""
Task: IMP-003 - Cash Register Parser (Calendar Grid Layout)
Description: Parser for the Cash Register Excel with calendar grid.
PRD Section: 2.4 Daily cash register Excel
"""

from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import date
from src.importers.base import BaseImporter
from src.models.cash_register import CashRegisterEntry
from src.config.settings import settings
import dateutil.parser

class CashRegisterImporter(BaseImporter):
    """
    Implements the complex logic for parsing the calendar-grid Cash Register.

    This parser handles:
    - Identifying the correct year sheet.
    - Mapping month columns and day rows.
    - Handling cross-month lookups for prior balances.
    - Calculating derived cash signals.

    Attributes:
        session: SQLAlchemy session.
        run_id: The current reconciliation run ID.
    """

    def parse_file(self, file_path: str, column_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Reads the Cash Register file.

        Args:
            file_path: Path to the Excel file.
            column_mapping: Mapping of month names to column indices/names.
                            Required: year_sheet_name, month_cols (dict).

        Returns:
            List of dictionaries containing daily cash entries.
        """
        try:
            # We need to read specific sheet for the year
            sheet_name = column_mapping.get("year_sheet_name", str(date.today().year))
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        except Exception as e:
            raise ValueError(f"Failed to read file/sheet '{sheet_name}': {e}")

        # The grid is: Rows = Days (1-31), Cols = Months (Jan-Dec)
        # We need mapping: which column index corresponds to which month
        # Assuming column_mapping provides 'month_col_map': {'Jan': 1, 'Feb': 4, ...}
        # Or more simply, let's assume standard layout or simple mapping

        # For MVP, let's assume a standard layout where:
        # Row 0: Header (Months)
        # Rows 1-31: Data for days 1-31
        # Cols: Jan, Feb, ...

        # Let's try to infer or use provided map
        month_map = column_mapping.get("month_col_map", {})
        # Example: {"January": "B", "February": "E"} -> normalized to indices

        # If not provided, we might need a more sophisticated detection or assume specific columns
        # Let's assume the dataframe has month names in first row

        normalized_data = []

        # Identify month columns
        header_row = df.iloc[0]
        month_cols = {}
        for idx, val in header_row.items():
            if isinstance(val, str):
                try:
                    # Parse month name to number
                    dt = dateutil.parser.parse(f"1 {val} 2000")
                    month_cols[dt.month] = idx
                except:
                    pass

        if not month_cols:
             raise ValueError("Could not identify month columns in header row.")

        # Parse grid
        year = int(sheet_name)
        for day in range(1, 32):
            # Find row index for this day. Assuming rows 1-31 map to days 1-31
            # Adjust if there are extra header rows
            row_idx = day # Row 1 is Day 1
            if row_idx >= len(df):
                break

            row = df.iloc[row_idx]

            for month, col_idx in month_cols.items():
                try:
                    entry_date = date(year, month, day)
                except ValueError:
                    continue # Invalid date (e.g., Feb 30)

                balance = self._parse_amount(row[col_idx])

                # We need prior balance for derived signal
                # For now, just capture the raw balance. Calculation happens in persist or later step?
                # The PRD says "For a selected date d, read C_d, C_(d-1)..."
                # It might be better to capture all data first, then compute derived signals.

                normalized_data.append({
                    "entry_date": entry_date,
                    "closing_balance": balance,
                    "raw_data": {"row": row_idx, "col": col_idx, "val": row[col_idx]}
                })

        return normalized_data

    def persist_data(self, data: List[Dict[str, Any]]) -> int:
        """
        Saves cash entries and computes derived signals.
        """
        # First, bulk upsert the raw balances
        for item in data:
            entry = self.session.query(CashRegisterEntry).filter_by(entry_date=item["entry_date"]).first()
            if entry:
                entry.closing_balance = item["closing_balance"]
                entry.raw_data = item["raw_data"]
            else:
                entry = CashRegisterEntry(
                    entry_date=item["entry_date"],
                    closing_balance=item["closing_balance"],
                    raw_data=item["raw_data"]
                )
                self.session.add(entry)

        self.session.flush() # Commit raw data to allow queries

        # Second pass: Compute derived signals (C_d - C_prev + Expenses)
        # This requires querying the just-saved data
        count = 0
        for item in data:
            current_date = item["entry_date"]
            entry = self.session.query(CashRegisterEntry).filter_by(entry_date=current_date).first()

            if entry.closing_balance is not None:
                # Find previous valid balance (up to 5 days back)
                prior_balance = 0.0
                prior_entry = None
                for i in range(1, 6):
                    prev_date = current_date - pd.Timedelta(days=i)
                    prior_entry = self.session.query(CashRegisterEntry).filter_by(entry_date=prev_date).first()
                    if prior_entry and prior_entry.closing_balance is not None:
                        prior_balance = prior_entry.closing_balance
                        break

                entry.prior_closing_balance = prior_balance
                # Derived cash from orders = (Closing - Opening) + Expenses
                # Expenses defaults to 0 if not entered manually
                expenses = float(entry.expenses_deposits or 0)
                entry.derived_cash_from_orders = float(entry.closing_balance) - float(prior_balance) + expenses

                if prior_entry:
                     entry.validation_status = 'valid'
                else:
                     entry.validation_status = 'partial' # Missing prior data

            count += 1

        self.session.commit()
        return count

    def _parse_amount(self, amount_val: Any) -> Optional[float]:
        """Parses numeric amount."""
        if pd.isna(amount_val) or amount_val == "":
            return None # Distinct from 0.0 for missing data
        if isinstance(amount_val, (int, float)):
            return float(amount_val)
        try:
            clean_val = str(amount_val).replace('₹', '').replace(',', '').strip()
            return float(clean_val)
        except:
            return None
