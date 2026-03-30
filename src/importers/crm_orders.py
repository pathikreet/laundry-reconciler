"""
CRM Orders Report Importer.

Imports authoritative order data from the CRM Orders Report. If an order
already exists (from Sales import), updates it with the authoritative
Net Amount. Does NOT create PaymentEvents (Sales report handles payments).
"""

import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter, read_excel_auto, sanitize_raw_data
from src.models.orders import Order

logger = logging.getLogger(__name__)


class CRMOrdersImporter(BaseImporter):

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
            # Orders report uses 'Order No.' instead of 'Order Number'
            order_number = str(row.get('Order No.', '') or row.get('Order Number', '') or '').strip()
            if not order_number:
                continue

            normalized.append({
                'order_number': order_number,
                'customer_name': str(row.get('Name', '') or row.get('Customer Name', '') or '').strip(),
                'customer_code': str(row.get('Customer Code', '') or '').strip() or None,
                'order_date': self._parse_date(row.get('Order Date / Time') or row.get('Order Date')),
                'net_amount': self._parse_amount(row.get('Net Amount', 0)),
                'advance': self._parse_amount(row.get('Advance', 0)),
                'paid': self._parse_amount(row.get('Paid', 0)),
                'adjustment': self._parse_amount(row.get('Adjustment', 0)),
                'balance': self._parse_amount(row.get('Balance', 0)),
                'pcs': self._parse_int(row.get('Pcs.', 0)),
                'due_date': self._parse_date(row.get('Due Date')),
                'order_status': str(row.get('Order Status', '') or '').strip() or None,
                'package': str(row.get('Package', '') or '').strip(),
                'home_delivery': str(row.get('Home Delivery', '') or '').strip(),
                'raw_data': row
            })
        return normalized

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out summary rows and entries without order_date."""
        valid = []
        for row in data:
            if not row['order_number']:
                continue
            if row['order_date'] is None:
                logger.debug("Skipping row with no parseable order_date (summary row)")
                continue
            valid.append(row)
        return valid

    def save(self, data: List[Dict[str, Any]]) -> None:
        for row in data:
            order = self.db.query(Order).filter_by(
                order_number=row['order_number']
            ).first()

            if order:
                # Update with authoritative Net Amount
                order.order_amount = row['net_amount']
                order.adjustments = row['adjustment']
                order.balance = row['balance']
                if row['customer_name']:
                    order.customer_name = row['customer_name']
                # Enrich raw_data with Orders report fields
                enriched = order.raw_data or {}
                enriched['_orders_report'] = {
                    'net_amount': row['net_amount'],
                    'advance': row['advance'],
                    'due_date': str(row['due_date']) if row['due_date'] else None,
                    'order_status': row['order_status'],
                    'pcs': row['pcs'],
                    'package': row['package'],
                    'home_delivery': row['home_delivery'],
                }
                order.raw_data = enriched
                logger.info("Updated order %s with Net Amount=%.2f", row['order_number'], row['net_amount'])
            else:
                # Create new order from Orders report
                order = Order(
                    order_number=row['order_number'],
                    customer_code=row.get('customer_code'),
                    customer_name=row['customer_name'],
                    order_date=row['order_date'],
                    order_amount=row['net_amount'],
                    payment_received=row['paid'],
                    adjustments=row['adjustment'],
                    balance=row['balance'],
                    type='Order',
                    raw_data=row['raw_data']
                )
                self.db.add(order)

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

    def _parse_int(self, val: Any) -> int:
        try:
            return int(float(str(val).strip()))
        except (ValueError, TypeError):
            return 0
