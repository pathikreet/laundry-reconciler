import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter
from src.models.orders import Order
from src.models.payments import PaymentEvent

class CRMImporter(BaseImporter):
    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        # Replace NaN with None
        df = df.where(pd.notnull(df), None)
        return df.to_dict(orient='records')

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_data = []
        for row in raw_data:
            # Handle potential different column names or mapping here if needed
            # For now, we assume standard headers as per PRD

            order_number = str(row.get('Order Number', '') or '').strip()
            if not order_number:
                continue

            normalized_row = {
                'order_number': order_number,
                'customer_name': str(row.get('Customer Name', '') or '').strip(),
                'order_date': self._parse_date(row.get('Order Date')),
                'delivery_date': self._parse_date(row.get('Delivery Date')),
                'order_amount': self._parse_amount(row.get('Order Amount')),
                'payment_received': self._parse_amount(row.get('Payment Amount')),
                'adjustments': self._parse_amount(row.get('Adjustments', 0)),
                'payment_mode': str(row.get('Payment Mode', '') or '').strip(),
                'payment_date': self._parse_date(row.get('Payment Date')),
                'raw_data': row
            }
            # Balance calculation
            normalized_row['balance'] = normalized_row['order_amount'] - normalized_row['payment_received']
            normalized_data.append(normalized_row)
        return normalized_data

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Basic validation: filter out rows without order number
        return [row for row in data if row['order_number']]

    def save(self, data: List[Dict[str, Any]]) -> None:
        for row in data:
            # Create or update Order
            order = self.db.query(Order).filter_by(order_number=row['order_number']).first()
            if not order:
                order = Order(
                    order_number=row['order_number'],
                    customer_name=row['customer_name'],
                    order_date=row['order_date'],
                    order_amount=row['order_amount'],
                    payment_received=row['payment_received'],
                    adjustments=row['adjustments'],
                    balance=row['balance'],
                    raw_data=row['raw_data']
                )
                self.db.add(order)
                self.db.flush() # flush to get ID
            else:
                # Update existing order fields if necessary
                order.customer_name = row['customer_name']
                order.order_date = row['order_date'] if row['order_date'] else order.order_date
                order.order_amount = row['order_amount']
                order.payment_received = row['payment_received']
                order.adjustments = row['adjustments']
                order.balance = row['balance']
                # Merge raw data? Or keep original? Let's keep latest.
                order.raw_data = row['raw_data']


            # Create PaymentEvent if there is a payment
            # Logic: If payment_received > 0, create a payment event.
            if row['payment_received'] > 0:
                payment_date = row['payment_date']
                # If payment date is missing but there is an amount, use order date or today?
                # PRD says "Payment Date (date; may be blank)".
                # If blank, we might not be able to assign it to a day.
                # But for now, let's require a date or skip creating the event (or flag it).

                if payment_date:
                     # Check if payment already exists to avoid duplicates
                    existing_payment = self.db.query(PaymentEvent).filter_by(
                        order_id=order.id,
                        source='crm',
                        amount=row['payment_received'],
                        payment_date=payment_date
                    ).first()

                    if not existing_payment:
                        payment = PaymentEvent(
                            order_id=order.id,
                            source='crm',
                            payment_date=payment_date,
                            amount=row['payment_received'],
                            payment_mode=row['payment_mode'],
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
