import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter
from src.models.payments import PaymentEvent

logger = logging.getLogger(__name__)

class MSwipeImporter(BaseImporter):
    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        df = df.where(pd.notnull(df), None)
        return df.to_dict(orient='records')

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_data = []
        for row in raw_data:
            # Helper to get value from multiple possible keys
            def get_val(keys):
                for k in keys:
                    if row.get(k) is not None and str(row.get(k)).strip() != '':
                        return row.get(k)
                return None

            # Status check
            status_keys = ['Status', 'Trx Status', 'Transaction Status']
            status_val = get_val(status_keys)

            # If status column exists, check it.
            if status_val:
                status = str(status_val).lower()
                if 'success' not in status and 'approved' not in status:
                     continue

            # If no status column, rely on amount > 0 check below.

            amount = self._parse_amount(get_val(['NetAmt', 'FinalPayment', 'TxnAmt', 'Amount']))
            if amount <= 0:
                continue

            # Date (prefer transaction/customer payment date over merchant settlement date)
            date_val = get_val(['TxnDate', 'TransactionDate', 'Transaction Date', 'PaymentDate', 'Payment Date'])
            payment_date = self._parse_date(date_val)
            if not payment_date:
                continue

            # Mode
            mode = str(get_val(['Interchange', 'CardType', 'PayeeVPA', 'PaymentMode']) or 'Card').strip()

            # Ref IDs
            ref_id = str(get_val(['RR_NO', 'Stan_No', 'Mswipe_Ref_No', 'ARN', 'RefId']) or '').strip()

            normalized_row = {
                'payment_date': payment_date,
                'amount': amount,
                'payment_mode': mode,
                'original_mode': mode,
                'ref_id': ref_id,
                'raw_data': row
            }
            normalized_data.append(normalized_row)
        return normalized_data

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Ensure date and amount are present
        return [row for row in data if row['payment_date'] and row['amount'] > 0]

    def save(self, data: List[Dict[str, Any]]) -> None:
        # Get dates present in this import batch
        run_dates = set()
        for r in data:
            if r.get('payment_date'):
                run_dates.add(r['payment_date'])

        # Clear old MSWIPE events FOR THESE DATES so re-importing doesn't duplicate
        if run_dates:
            deleted = self.db.query(PaymentEvent).filter(
                PaymentEvent.source == 'mswipe',
                PaymentEvent.payment_date.in_(run_dates)
            ).delete(synchronize_session=False)
            if deleted:
                logger.info("Cleared %d existing MSWIPE payment events before re-import", deleted)
                self.db.flush()
        for row in data:

            query = self.db.query(PaymentEvent).filter_by(
                source='mswipe',
                payment_date=row['payment_date'],
                amount=row['amount']
            )

            existing = query.all()

            # We need to check if ANY of existing has the same ref_id in their JSON.
            is_duplicate = False
            for p in existing:
                if p.mswipe_ref_ids and row['ref_id'] and row['ref_id'] in p.mswipe_ref_ids:
                    is_duplicate = True
                    break
                # If no ref_id in row, but exact amount/date/mode match?
                # Without ref_id, duplicate amounts on same day are indistinguishable.
                # Assuming unique transactions if ref_id is present.

            if not is_duplicate:
                payment = PaymentEvent(
                    source='mswipe',
                    payment_date=row['payment_date'],
                    amount=row['amount'],
                    payment_mode=self._normalize_mode(row['payment_mode']),
                    original_mode=row['original_mode'],
                    mswipe_ref_ids=[row['ref_id']] if row['ref_id'] else [],
                    raw_data=row['raw_data']
                )
                self.db.add(payment)

        self.db.commit()

    def _parse_date(self, date_str: Any) -> Optional[Any]:
        if date_str is None or pd.isna(date_str) or str(date_str).strip() == '':
            return None
        try:
            return parse(str(date_str)).date()
        except:
            return None

    def _parse_amount(self, amount: Any) -> float:
        if amount is None or pd.isna(amount) or str(amount).strip() == '':
            return 0.0
        try:
            return float(str(amount).replace(',', '').replace('₹', '').strip())
        except:
            return 0.0

    def _normalize_mode(self, mode: str) -> str:
        # PRD: "Any payment present in the MSWIPE transactions will be classified and shown as GPay (Google Pay/UPI)"
        return 'GPay'
