import pandas as pd
import logging
from typing import List, Dict, Any, Optional
from datetime import date as date_type
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter
from src.models.deliveries import DeliveryEvent
from src.models.payments import PaymentEvent
from src.models.orders import Order
from src.config.settings import Settings

logger = logging.getLogger(__name__)

class NotepadImporter(BaseImporter):
    def __init__(self, db_session: Session, settings: Settings = None):
        super().__init__(db_session)
        self.settings = settings or Settings()
        self._known_modes = set(self.settings.payment_mode_mapping.values())

    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        sheet_name = kwargs.get('sheet_name', 0)  # Default: first sheet
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            if sheet_name == '__all__' or isinstance(sheet_name, list):
                # Read specified sheets (or all) and combine
                read_arg = None if sheet_name == '__all__' else sheet_name
                all_sheets = pd.read_excel(file_path, sheet_name=read_arg)
                frames = []
                for name, sheet_df in all_sheets.items():
                    sheet_df['_sheet_name'] = name  # Track which sheet each row came from
                    frames.append(sheet_df)
                df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            else:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
        df = df.where(pd.notnull(df), None)
        return df.to_dict(orient='records')

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_data = []
        for row in raw_data:
            # Fields: Order Number, Customer Name, Amount, Mode, Date, Runner, Notes

            # Helper to get value
            def get_val(keys):
                for k in keys:
                    if row.get(k) is not None and str(row.get(k)).strip() != '':
                        return row.get(k)
                return None

            date_val = get_val(['Date', 'Delivery Date', 'Time', 'Delivery Time'])
            delivery_date = self._parse_date(date_val)

            if not delivery_date:
                continue

            amount = self._parse_amount(get_val(['Amount', 'Amount Collected', 'Collection']))
            mode = str(get_val(['Mode', 'Payment Mode']) or '').strip()

            # Order Number is optional but useful for linking
            order_number = str(get_val(['Order Number', 'Order No', 'Order #']) or '').strip()

            customer_name = str(get_val(['Customer Name', 'Name', 'Customer']) or '').strip()
            runner_name = str(get_val(['Runner', 'Runner Name']) or '').strip()
            notes = str(get_val(['Notes', 'Note', 'Remarks']) or '').strip()

            normalized_row = {
                'delivery_date': delivery_date,
                'amount_collected': amount,
                'payment_mode': mode,
                'order_number': order_number, # Not stored in DeliveryEvent directly but used to link
                'customer_name': customer_name,
                'runner_name': runner_name,
                'notes': notes,
                'raw_data': {k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                             for k, v in row.items()}
            }
            normalized_data.append(normalized_row)
        return normalized_data

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [row for row in data if row['delivery_date']]

    def save(self, data: List[Dict[str, Any]]) -> None:
        # Get dates present in this import batch
        run_dates = set()
        for r in data:
            if r.get('delivery_date'):
                run_dates.add(r['delivery_date'])

        # Clear old notepad events FOR THESE DATES so re-importing doesn't duplicate
        if run_dates:
            del_d = self.db.query(DeliveryEvent).filter(
                DeliveryEvent.source == 'notepad',
                DeliveryEvent.delivery_date.in_(run_dates)
            ).delete(synchronize_session=False)
            del_p = self.db.query(PaymentEvent).filter(
                PaymentEvent.source == 'notepad',
                PaymentEvent.payment_date.in_(run_dates)
            ).delete(synchronize_session=False)
            if del_d or del_p:
                logger.info("Cleared %d delivery, %d payment events (notepad) before re-import", del_d, del_p)
                self.db.flush()

        for row in data:
            # Try to link to order if order_number provided
            order = None
            order_id = None
            if row['order_number']:
                order = self.db.query(Order).filter_by(order_number=row['order_number']).first()
                if order:
                    order_id = order.id

            # Resolve payment mode: use notepad if recognized, else fall back to CRM
            notepad_mode = self._normalize_mode(row['payment_mode'])
            final_mode = notepad_mode

            if not notepad_mode or notepad_mode not in self._known_modes:
                # Unrecognized/empty — try to derive from CRM payments for this order
                crm_mode = self._get_crm_payment_mode(order) if order else None
                if crm_mode:
                    logger.info(
                        "Notepad mode '%s' unrecognized for %s, using CRM mode: %s",
                        row['payment_mode'], row.get('order_number', '?'), crm_mode
                    )
                    final_mode = crm_mode
                else:
                    # No CRM data — mark as Unknown (don't default to Cash, would skew cash totals)
                    final_mode = 'Unknown'
                    self.errors.append({
                        'order_number': row.get('order_number', '?'),
                        'reason': f"Unrecognized payment mode '{row['payment_mode']}' and no CRM data to derive from",
                    })
                    logger.warning(
                        "Notepad mode '%s' unrecognized for %s, no CRM data — marked as Unknown",
                        row['payment_mode'], row.get('order_number', '?')
                    )

            # Create DeliveryEvent (stores original notepad mode for audit)
            delivery = DeliveryEvent(
                order_id=order_id,
                source='notepad',
                delivery_date=row['delivery_date'],
                customer_name=row['customer_name'],
                amount_collected=row['amount_collected'],
                payment_mode=row['payment_mode'],  # Original notepad mode for audit
                runner_name=row['runner_name'],
                notes=row['notes'],
                raw_data=row['raw_data']
            )
            self.db.add(delivery)

            # "Due" = payment pending → delivery recorded, NO PaymentEvent created
            # This feeds into the CreditPolicyViolation check during reconciliation
            if final_mode == 'Due':
                logger.info(
                    "Order %s marked as Due (payment pending) — no PaymentEvent created",
                    row.get('order_number', '?')
                )
                continue

            # Create PaymentEvent if amount > 0
            if row['amount_collected'] > 0:
                payment = PaymentEvent(
                    order_id=order_id,
                    source='notepad',
                    payment_date=row['delivery_date'], # Assuming collected on delivery
                    amount=row['amount_collected'],
                    payment_mode=final_mode,           # Resolved mode (CRM fallback)
                    original_mode=row['payment_mode'],  # Original notepad mode for audit
                    raw_data=row['raw_data']
                )
                self.db.add(payment)

        self.db.commit()

    def _get_crm_payment_mode(self, order: Order) -> Optional[str]:
        """Get the most common CRM payment mode for this order."""
        crm_payments = [p for p in order.payments if p.source == 'crm']
        if not crm_payments:
            return None
        # Return the mode from the most recent CRM payment
        crm_payments.sort(key=lambda p: p.payment_date or '', reverse=True)
        return crm_payments[0].payment_mode

    def _parse_date(self, date_str: Any) -> Optional[Any]:
        """Parse date with dayfirst=True for Indian DD/MM/YYYY convention.
        Handles pandas Timestamps directly to avoid string conversion issues."""
        if date_str is None:
            return None
        # Handle pandas Timestamp / datetime objects directly
        if hasattr(date_str, 'date'):
            return date_str.date()
        if isinstance(date_str, date_type):
            return date_str
        s = str(date_str).strip()
        if not s or s.lower() == 'nan' or s.lower() == 'nat':
            return None
        try:
            return parse(s, dayfirst=True).date()
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
        """Map notepad mode to a known mode using settings mapping."""
        if not mode:
            return ''
        m = mode.strip().lower()
        return self.settings.payment_mode_mapping.get(m, mode)

