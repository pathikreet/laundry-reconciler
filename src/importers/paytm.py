"""
Company Paytm QR payment importer.

Parses Paytm settlement CSV files and stores them as PaymentEvents
with source='paytm'. These are actual online payment receipts from
the company Paytm QR code, alongside MSWIPE.
"""

import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.importers.base import BaseImporter, sanitize_raw_data
from src.models.payments import PaymentEvent

logger = logging.getLogger(__name__)


class PaytmImporter(BaseImporter):
    """
    Imports Company Paytm QR payment transactions.

    CSV columns:
        Transaction No. | Transaction Date | Is Reconcile |
        MID No | Amount | Commission | UTR No | Store Code
    """

    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        """Parse the Paytm CSV file."""
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, parse_dates=False)
        else:
            df = pd.read_excel(file_path, parse_dates=False)

        df = df.where(pd.notnull(df), None)
        logger.info("Read %d rows from Paytm file", len(df))
        return [sanitize_raw_data(row) for row in df.to_dict(orient='records')]

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize Paytm data into payment events."""
        normalized = []
        for row in raw_data:
            # Parse amount
            amount = self._parse_amount(row.get('Amount'))
            if amount <= 0:
                continue

            # Parse date (DD-MM-YYYY format)
            date_val = row.get('Transaction Date')
            payment_date = self._parse_date(date_val)
            if not payment_date:
                self.errors.append({'row': row, 'error': f'Invalid date: {date_val}'})
                continue

            # Transaction reference
            txn_no = str(row.get('Transaction No.', '') or '').strip()
            utr_no = str(row.get('UTR No', '') or '').strip()
            ref_id = utr_no or txn_no

            # Commission
            commission = self._parse_amount(row.get('Commission'))

            normalized.append({
                'payment_date': payment_date,
                'amount': amount,
                'commission': commission,
                'payment_mode': 'Paytm',
                'ref_id': ref_id,
                'txn_no': txn_no,
                'raw_data': row,
            })

        return normalized

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate: date and positive amount required."""
        return [row for row in data if row['payment_date'] and row['amount'] > 0]

    def save(self, data: List[Dict[str, Any]]) -> None:
        """Save Paytm payments to database as PaymentEvents with source='paytm'."""
        # Get dates in this batch
        run_dates = set(r['payment_date'] for r in data if r.get('payment_date'))

        # Clear existing Paytm events for these dates (re-import safe)
        if run_dates:
            deleted = self.db.query(PaymentEvent).filter(
                PaymentEvent.source == 'paytm',
                PaymentEvent.payment_date.in_(run_dates),
            ).delete(synchronize_session=False)
            if deleted:
                logger.info("Cleared %d existing Paytm payment events before re-import", deleted)
                self.db.flush()

        for row in data:
            payment = PaymentEvent(
                source='paytm',
                payment_date=row['payment_date'],
                amount=row['amount'],
                payment_mode='Paytm',
                original_mode='Paytm QR',
                mswipe_ref_ids=[row['ref_id']] if row['ref_id'] else [],
                raw_data=row['raw_data'],
            )
            self.db.add(payment)

        logger.info("Saved %d Paytm payment events", len(data))

    def _parse_date(self, date_str: Any) -> Optional[Any]:
        """Parse DD-MM-YYYY date format."""
        if date_str is None or str(date_str).strip() == '':
            return None
        try:
            from datetime import date as date_cls
            s = str(date_str).strip()
            # DD-MM-YYYY
            if '-' in s:
                parts = s.split('-')
                if len(parts) == 3:
                    day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                    return date_cls(year, month, day)
            # Fallback
            from dateutil.parser import parse
            return parse(s, dayfirst=True).date()
        except Exception:
            return None

    def _parse_amount(self, amount: Any) -> float:
        if amount is None or str(amount).strip() == '':
            return 0.0
        try:
            return float(str(amount).replace(',', '').strip())
        except (ValueError, TypeError):
            return 0.0
