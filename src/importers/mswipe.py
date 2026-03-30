import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter, read_excel_auto, sanitize_raw_data
from src.models.payments import PaymentEvent

logger = logging.getLogger(__name__)

class MSwipeImporter(BaseImporter):
    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            try:
                df = read_excel_auto(file_path)
            except Exception:
                # MSWIPE often exports HTML tables disguised as .xls files.
                # When xlrd/openpyxl fails, try reading as HTML.
                logger.info("Standard Excel read failed, trying HTML table fallback for %s", file_path)
                try:
                    tables = pd.read_html(file_path)
                    df = tables[0] if tables else pd.DataFrame()
                    # pd.read_html may miss <thead> — if columns are numeric (0,1,2...),
                    # the real header is in row 0
                    first_col = df.columns[0]
                    is_numeric_header = not isinstance(first_col, str) or first_col.isdigit()
                    if not df.empty and is_numeric_header:
                        df.columns = df.iloc[0]
                        df = df.iloc[1:].reset_index(drop=True)
                except Exception as e:
                    logger.error("HTML fallback also failed for %s: %s", file_path, e)
                    raise
        df = df.where(pd.notnull(df), None)
        return [sanitize_raw_data(row) for row in df.to_dict(orient='records')]

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
            status_keys = ['Status', 'Trx Status', 'Transaction Status', 'Txn Status']
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
            date_val = get_val(['TxnDate', 'TransactionDate', 'Transaction Date', 'PaymentDate', 'Payment Date', 'Tx Date Time'])
            payment_date = self._parse_date(date_val)
            if not payment_date:
                continue

            # Mode
            mode = str(get_val(['Interchange', 'CardType', 'PayeeVPA', 'PaymentMode', 'Mode Of Payment']) or 'Card').strip()

            # Ref IDs
            ref_id = str(get_val(['RR_NO', 'Stan_No', 'Mswipe_Ref_No', 'ARN', 'RefId', 'RR No']) or '').strip()

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
            d = r.get('payment_date')
            if d:
                run_dates.add(d)

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
        """Parse MSWIPE date strings which come in two formats:
        
        1. MM/DD/YYYY HH:MM:SS  (slash-separated, US format)
        2. YYYY-DD-MM HH:MM:SS  (dash-separated, day/month SWAPPED by Excel)
        
        Excel's cell protection can produce YYYY-DD-MM dates instead of
        YYYY-MM-DD. We handle this with:
          - If first value > 12: definitely a day, so swap (unambiguous)
          - If both <= 12: try default parse; if result is in the future,
            try swapping — if swap gives a past date, use that instead.
        """
        if date_str is None or pd.isna(date_str) or str(date_str).strip() == '':
            return None
        try:
            s = str(date_str).strip()
            from datetime import date as date_cls
            today = date_cls.today()
            
            # Format 1: MM/DD/YYYY — handle with dayfirst=False
            if '/' in s:
                return parse(s, dayfirst=False).date()
            
            # Format 2: YYYY-A-B (dash-separated ISO-like)
            date_part = s.split(' ')[0] if ' ' in s else s
            parts = date_part.split('-')
            if len(parts) == 3:
                year_s, a_s, b_s = parts
                year, a, b = int(year_s), int(a_s), int(b_s)
                
                # Unambiguous: a > 12 means a is definitely a day
                if a > 12 and 1 <= b <= 12:
                    try:
                        return date_cls(year, b, a)
                    except ValueError:
                        pass
                
                # Ambiguous: both <= 12 — default to YYYY-MM-DD,
                # but if result is in the future, try YYYY-DD-MM
                if a <= 12 and b <= 12 and a != b:
                    default_date = date_cls(year, a, b)  # YYYY-MM-DD
                    if default_date > today:
                        # Try swapping: YYYY-DD-MM
                        try:
                            swapped = date_cls(year, b, a)
                            if swapped <= today:
                                return swapped
                        except ValueError:
                            pass
                    return default_date
            
            # Default parse for any other format
            return parse(s, dayfirst=False).date()
        except Exception:
            return None

    def _parse_amount(self, amount: Any) -> float:
        if amount is None or pd.isna(amount) or str(amount).strip() == '':
            return 0.0
        try:
            return float(str(amount).replace(',', '').replace('\u20b9', '').strip())
        except:
            return 0.0

    def _normalize_mode(self, mode: str) -> str:
        # PRD: "Any payment present in the MSWIPE transactions will be classified and shown as GPay (Google Pay/UPI)"
        return 'GPay'
