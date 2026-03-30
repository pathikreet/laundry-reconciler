"""
CRM Sales Report Importer.

Handles the CRM Sales & Delivery Export which contains one row per payment
transaction. The same order may appear multiple times (advance, delivery,
post-delivery payments).

Import logic:
1. Sort rows by payment_date to get chronological order
2. Group rows by order_number
3. Aggregate: one Order record + N PaymentEvent records per group
"""

import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from collections import defaultdict
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter, read_excel_auto, sanitize_raw_data
from src.models.orders import Order
from src.models.payments import PaymentEvent

logger = logging.getLogger(__name__)


class CRMImporter(BaseImporter):

    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = read_excel_auto(file_path)
        df = df.where(pd.notnull(df), None)
        return [sanitize_raw_data(row) for row in df.to_dict(orient='records')]

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for row in raw_data:
            order_number = str(row.get('Order Number', '') or '').strip()
            if not order_number:
                continue

            payment_received = self._parse_amount(
                row.get('Payment Received') or row.get('Payment Amount') or 0
            )
            payment_mode = str(row.get('Payment Mode', '') or '').strip()

            normalized.append({
                'order_number': order_number,
                'customer_name': str(row.get('Customer Name', '') or '').strip(),
                'customer_code': str(row.get('Customer Code', '') or '').strip() or None,
                'customer_address': str(row.get('Customer Address', '') or '').strip() or None,
                'customer_mobile': str(row.get('Customer Mobile No.', '') or '').strip() or None,
                'order_date': self._parse_date(row.get('Order Date')),
                'payment_date': self._parse_date(row.get('Payment Date')),
                'payment_received': payment_received,
                'adjustments': self._parse_amount(row.get('Adjustments', 0)),
                'balance': self._parse_amount(row.get('Balance', 0)),
                'payment_mode': payment_mode,
                'type': str(row.get('Type', '') or '').strip() or 'Order',
                'raw_data': row
            })
        return normalized

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out summary/total rows (no parseable order_date)."""
        valid = []
        for row in data:
            if not row['order_number']:
                continue
            if row['order_date'] is None:
                # Summary/total rows — skip silently
                logger.debug("Skipping row with no parseable order_date (summary row)")
                continue
            valid.append(row)
        return valid

    def save(self, data: List[Dict[str, Any]]) -> None:
        """
        Save with multi-row order aggregation.

        1. Clear existing CRM payment events (idempotent re-import)
        2. Sort by payment_date (chronological)
        3. Group by order_number
        4. Create one Order + N PaymentEvents per group
        """
        # Get dates present in this import batch
        run_dates = set()
        for r in data:
            d = r.get('payment_date') or r.get('order_date')
            if d:
                run_dates.add(d)

        # Clear old CRM payment events FOR THESE DATES so re-importing doesn't duplicate
        if run_dates:
            deleted = self.db.query(PaymentEvent).filter(
                PaymentEvent.source == 'crm',
                PaymentEvent.payment_date.in_(run_dates)
            ).delete(synchronize_session=False)
            if deleted:
                logger.info("Cleared %d existing CRM payment events before re-import", deleted)
                self.db.flush()
        # Sort by payment_date so last row has the final balance
        sorted_data = sorted(data, key=lambda r: r['payment_date'] or r['order_date'])

        # Group by order_number
        groups = defaultdict(list)
        for row in sorted_data:
            groups[row['order_number']].append(row)

        for order_number, rows in groups.items():
            # Aggregate totals across all payment rows
            total_paid = sum(r['payment_received'] for r in rows)
            total_adj = sum(r['adjustments'] for r in rows)
            final_balance = rows[-1]['balance']  # last row (chronologically) has the final balance

            # Derive order_amount if not provided in a dedicated column
            order_amount = total_paid + total_adj + final_balance

            # Use the first row for order metadata
            first = rows[0]

            # Create or update Order
            order = self.db.query(Order).filter_by(order_number=order_number).first()
            if not order:
                order = Order(
                    order_number=order_number,
                    customer_code=first.get('customer_code'),
                    customer_name=first['customer_name'],
                    customer_address=first.get('customer_address'),
                    customer_mobile=first.get('customer_mobile'),
                    order_date=first['order_date'],
                    order_amount=order_amount,
                    payment_received=total_paid,
                    adjustments=total_adj,
                    balance=final_balance,
                    type=first.get('type', 'Order'),
                    raw_data=first['raw_data']
                )
                self.db.add(order)
                self.db.flush()
            else:
                # Update with aggregated data
                order.order_amount = order_amount
                order.payment_received = total_paid
                order.adjustments = total_adj
                order.balance = final_balance
                if first['customer_name']:
                    order.customer_name = first['customer_name']
                order.raw_data = first['raw_data']

            # Create PaymentEvents — one per payment row with amount > 0
            # Create one PaymentEvent per payment row (each row is a distinct transaction)
            for row in rows:
                if row['payment_received'] <= 0:
                    continue
                if not row['payment_date']:
                    logger.warning("Skipping payment for %s: no payment_date", order_number)
                    continue

                payment = PaymentEvent(
                    order_id=order.id,
                    source='crm',
                    payment_date=row['payment_date'],
                    amount=row['payment_received'],
                    payment_mode=row['payment_mode'],
                    original_mode=row['payment_mode'],
                    raw_data=row['raw_data']
                )
                self.db.add(payment)

            if len(rows) > 1:
                logger.info(
                    "Order %s: aggregated %d payment rows (total=%.2f, balance=%.2f)",
                    order_number, len(rows), total_paid, final_balance
                )

    def _parse_date(self, date_str: Any) -> Optional[Any]:
        if date_str is None or (isinstance(date_str, float) and pd.isna(date_str)) or str(date_str).strip() == '':
            return None
        try:
            return parse(str(date_str)).date()
        except Exception:
            return None

    def _parse_amount(self, amount: Any) -> float:
        if amount is None or (isinstance(amount, float) and pd.isna(amount)) or str(amount).strip() == '':
            return 0.0
        try:
            return float(str(amount).replace(',', '').replace('₹', '').strip())
        except Exception:
            return 0.0
