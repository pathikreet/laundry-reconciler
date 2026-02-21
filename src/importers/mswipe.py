"""
Task: IMP-002 - MSWIPE Transactions Parser
Description: Parser for MSWIPE Excel/CSV transaction logs.
PRD Section: 2.3 MSWIPE daily payments export (Excel/CSV)
"""

from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime, date
from src.importers.base import BaseImporter
from src.models.payments import PaymentEvent
from src.config.settings import settings
import dateutil.parser
import json

class MSwipeImporter(BaseImporter):
    """
    Implements the import logic for MSWIPE transaction exports.

    This parser handles:
    - Filtering successful transactions.
    - Day-bucketing based on PaymentDate or TxnDate.
    - Identifying Google Pay/UPI transactions.
    - Capturing reference IDs for linking.

    Attributes:
        session: SQLAlchemy session.
        run_id: The current reconciliation run ID.
    """

    def parse_file(self, file_path: str, column_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Reads the MSWIPE export file and normalizes it.

        Args:
            file_path: Path to the MSWIPE export file.
            column_mapping: Mapping of internal field names to file column headers.
                            Required keys: txn_date, amount, status.
                            Optional: payment_mode, reference_id, payee_vpa.

        Returns:
            List of dictionaries containing normalized payment event data.
        """
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)
        except Exception as e:
            raise ValueError(f"Failed to read file: {e}")

        # Validate required columns
        required_cols = ["txn_date", "amount"]
        for key in required_cols:
             if key not in column_mapping or column_mapping[key] not in df.columns:
                 # Check if the column is present in the dataframe but not mapped
                 # If mapped but not in df, raise error
                 if key in column_mapping and column_mapping[key] not in df.columns:
                     raise ValueError(f"Required column '{column_mapping[key]}' not found in file.")
                 elif key not in column_mapping:
                     raise ValueError(f"Mapping for required field '{key}' is missing.")

        normalized_data = []
        for index, row in df.iterrows():
            try:
                # 1. Filter Successful Transactions
                # Heuristic: Amount > 0 and Status is Success (if present)
                amount = self._parse_amount(row.get(column_mapping.get("amount")))
                status_col = column_mapping.get("status")
                status = str(row.get(status_col, "")).lower() if status_col else "success"

                # If status column exists, check explicit failure
                if status_col and ("fail" in status or "declined" in status):
                    continue

                if amount <= 0:
                    continue

                # 2. Date Parsing & Day Bucketing
                txn_date_raw = row.get(column_mapping.get("txn_date"))
                payment_date = self._parse_date(txn_date_raw)
                if not payment_date:
                    print(f"Skipping row {index}: Invalid date {txn_date_raw}")
                    continue

                # 3. Payment Mode Identification
                # Default to Card/Other, check for UPI/GPay indicators
                mode_col = column_mapping.get("payment_mode")
                mode_raw = str(row.get(mode_col, "")).lower() if mode_col else ""

                vpa_col = column_mapping.get("payee_vpa")
                vpa = str(row.get(vpa_col, "")) if vpa_col else ""

                payment_mode = "Card" # Default for MSWIPE
                if "upi" in mode_raw or "bhim" in mode_raw or "gpay" in mode_raw or vpa:
                    payment_mode = "GPay" # Normalized as GPay per PRD

                # 4. Reference IDs
                ref_col = column_mapping.get("reference_id")
                ref_id = str(row.get(ref_col, "")) if ref_col else None

                payment_event = {
                    "source": "mswipe",
                    "payment_date": payment_date,
                    "amount": amount,
                    "payment_mode": payment_mode,
                    "original_mode": mode_raw,
                    "online_txn_id": ref_id,
                    "payee_vpa": vpa,
                    "mswipe_ref_ids": [ref_id] if ref_id else [],
                    "raw_data": row.to_dict()
                }

                normalized_data.append(payment_event)

            except Exception as e:
                print(f"Error parsing row {index}: {e}")
                continue

        return normalized_data

    def persist_data(self, data: List[Dict[str, Any]]) -> int:
        """
        Saves parsed MSWIPE transactions to the database.

        Creates PaymentEvent records.
        """
        count = 0
        for item in data:
            # Check for duplicates?
            # Simple check: same date, amount, and ref_id (if present)
            existing_query = self.session.query(PaymentEvent).filter(
                PaymentEvent.source == "mswipe",
                PaymentEvent.payment_date == item["payment_date"],
                PaymentEvent.amount == item["amount"]
            )

            if item["online_txn_id"]:
                existing_query = existing_query.filter(PaymentEvent.online_txn_id == item["online_txn_id"])

            if not existing_query.first():
                event = PaymentEvent(
                    source=item["source"],
                    payment_date=item["payment_date"],
                    amount=item["amount"],
                    payment_mode=item["payment_mode"],
                    original_mode=item["original_mode"],
                    online_txn_id=item["online_txn_id"],
                    payee_vpa=item["payee_vpa"],
                    mswipe_ref_ids=item["mswipe_ref_ids"],
                    raw_data=item["raw_data"]
                )
                self.session.add(event)
                count += 1

        self.session.commit()
        return count

    def _parse_date(self, date_val: Any) -> Optional[datetime.date]:
        """Parses date from various formats."""
        if pd.isna(date_val) or date_val == "":
            return None
        if isinstance(date_val, (datetime, date)):
             if isinstance(date_val, datetime):
                 return date_val.date()
             return date_val
        if isinstance(date_val, pd.Timestamp):
            return date_val.date()
        try:
            return dateutil.parser.parse(str(date_val)).date()
        except:
            return None

    def _parse_amount(self, amount_val: Any) -> float:
        """Parses numeric amount."""
        if pd.isna(amount_val) or amount_val == "":
            return 0.0
        if isinstance(amount_val, (int, float)):
            return float(amount_val)
        try:
            clean_val = str(amount_val).replace('₹', '').replace(',', '').strip()
            return float(clean_val)
        except:
            return 0.0
