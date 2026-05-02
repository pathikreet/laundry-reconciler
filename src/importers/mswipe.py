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
            df = pd.read_csv(file_path, parse_dates=False)
        else:
            try:
                # parse_dates=False keeps date columns as raw strings so
                # _parse_date can handle them explicitly (avoids ISO date bug).
                df = read_excel_auto(file_path, parse_dates=False)
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

        # Detect XLSX portal format: dates are MM/DD/YYYY but Excel may have
        # auto-converted some to YYYY-DD-MM (swapping month and day).
        # The 'Tx Date Time' column is unique to the XLSX transactions report.
        self._is_xlsx_portal = 'Tx Date Time' in df.columns
        if self._is_xlsx_portal:
            logger.info("Detected XLSX portal format (Tx Date Time column present)")

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

            # Mode (Switch_Card_Type is the XLSX equivalent of CardType/Interchange)
            mode = str(get_val(['Interchange', 'CardType', 'Switch_Card_Type', 'PayeeVPA',
                                'PaymentMode', 'Mode Of Payment', 'Card Holder Name']) or 'Card').strip()

            # Ref IDs (Voucher No is an XLSX-only unique txn reference)
            ref_id = str(get_val(['RR_NO', 'RR No', 'Stan_No', 'Stan No',
                                  'Mswipe_Ref_No', 'Voucher No', 'ARN', 'RefId']) or '').strip()
            # Strip leading apostrophe from RR No (XLSX portal adds it)
            if ref_id.startswith("'"):
                ref_id = ref_id[1:]

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
        """Parse MSWIPE date strings which come in multiple formats:
        
        1. MM/DD/YYYY HH:MM:SS  (slash-separated, US format — XLSX portal)
        2. DD-Mon-YYYY           (dash with month name — CSV portal)
        3. YYYY-DD-MM ...        (ISO-like but with day/month swapped by Excel)
        
        The XLSX portal exports dates as MM/DD/YYYY. When Excel encounters
        ambiguous dates (both components <= 12), it auto-converts them to
        ISO format but with month and day SWAPPED (YYYY-DD-MM instead of
        YYYY-MM-DD). We detect this via the _is_xlsx_portal flag set in
        import_data and swap them back.
        """
        if date_str is None or pd.isna(date_str) or str(date_str).strip() == '':
            return None
        try:
            import re
            from datetime import date as date_cls
            s = str(date_str).strip()
            
            # ISO-like format: YYYY-A-B (with optional time)
            iso_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
            if iso_match:
                year = int(iso_match.group(1))
                a = int(iso_match.group(2))  # Could be month or day
                b = int(iso_match.group(3))  # Could be day or month
                
                if getattr(self, '_is_xlsx_portal', False):
                    # XLSX portal: Excel swapped the original MM/DD to YYYY-DD-MM.
                    # Swap back: a=day, b=month → date(year, month=b, day=a)
                    try:
                        return date_cls(year, b, a)
                    except ValueError:
                        # If swap fails (e.g. b > 12), use as-is
                        return date_cls(year, a, b)
                else:
                    # CSV / other sources: treat as genuine YYYY-MM-DD
                    return date_cls(year, a, b)
            
            # Slash-separated: MM/DD/YYYY — US format, dayfirst=False
            if '/' in s:
                return parse(s, dayfirst=False).date()
            
            # Everything else (DD-Mon-YYYY, etc.) — default parse
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
