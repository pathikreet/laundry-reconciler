import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter
from src.models.deliveries import DeliveryEvent
from src.models.payments import PaymentEvent
from src.models.orders import Order

class NotepadImporter(BaseImporter):
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
            mode = str(get_val(['Mode', 'Payment Mode']) or 'Cash').strip()

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
                'raw_data': row
            }
            normalized_data.append(normalized_row)
        return normalized_data

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [row for row in data if row['delivery_date']]

    def save(self, data: List[Dict[str, Any]]) -> None:
        for row in data:
            # Try to link to order if order_number provided
            order_id = None
            if row['order_number']:
                order = self.db.query(Order).filter_by(order_number=row['order_number']).first()
                if order:
                    order_id = order.id

            # Create DeliveryEvent
            delivery = DeliveryEvent(
                order_id=order_id,
                source='notepad',
                delivery_date=row['delivery_date'],
                customer_name=row['customer_name'],
                amount_collected=row['amount_collected'],
                payment_mode=row['payment_mode'],
                runner_name=row['runner_name'],
                notes=row['notes'],
                raw_data=row['raw_data']
            )
            self.db.add(delivery)

            # Create PaymentEvent if amount > 0
            if row['amount_collected'] > 0:
                payment = PaymentEvent(
                    order_id=order_id,
                    source='notepad',
                    payment_date=row['delivery_date'], # Assuming collected on delivery
                    amount=row['amount_collected'],
                    payment_mode=self._normalize_mode(row['payment_mode']),
                    original_mode=row['payment_mode'],
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
        # Normalize to 'Cash', 'GPay', etc.
        m = mode.lower()
        if 'cash' in m:
            return 'Cash'
        if 'paytm' in m or 'gpay' in m or 'upi' in m or 'google' in m:
            return 'GPay'
        return mode
