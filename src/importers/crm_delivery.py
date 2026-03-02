"""
CRM Delivery Report Importer.

Imports delivery data from the CRM Delivery Report, creating DeliveryEvent
records linked to existing Order records by order_number.
"""

import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from dateutil.parser import parse
from src.importers.base import BaseImporter
from src.models.orders import Order
from src.models.deliveries import DeliveryEvent

logger = logging.getLogger(__name__)


class CRMDeliveryImporter(BaseImporter):

    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
        df = df.where(pd.notnull(df), None)
        return df.to_dict(orient='records')

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for row in raw_data:
            order_number = str(row.get('Order Number', '') or '').strip()
            if not order_number:
                continue

            normalized.append({
                'order_number': order_number,
                'customer_name': str(row.get('Customer Name', '') or '').strip(),
                'order_date': self._parse_date(row.get('Order Date')),
                'delivery_date': self._parse_date(row.get('Delivery Date')),
                'pcs_delivered': self._parse_int(row.get('Pcs Delivered', 0)),
                'pcs_balance': self._parse_float(row.get('Pcs Balance', 0)),
                'accepted_by': str(row.get('Accepted By', '') or '').strip() or None,
                'delivered_at': str(row.get('Delivered At', '') or '').strip() or None,
                'raw_data': row
            })
        return normalized

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out summary rows (no delivery_date) and empty entries."""
        valid = []
        for row in data:
            if not row['order_number']:
                continue
            if row['delivery_date'] is None:
                logger.debug("Skipping row with no parseable delivery_date (summary row)")
                continue
            valid.append(row)
        return valid

    def save(self, data: List[Dict[str, Any]]) -> None:
        for row in data:
            # Find linked Order
            order = self.db.query(Order).filter_by(
                order_number=row['order_number']
            ).first()

            order_id = order.id if order else None
            amount_collected = float(order.payment_received) if order else 0.0

            # Check for duplicate delivery
            existing = self.db.query(DeliveryEvent).filter_by(
                source='crm',
                order_id=order_id,
                delivery_date=row['delivery_date']
            ).first() if order_id else None

            if not existing:
                delivery = DeliveryEvent(
                    order_id=order_id,
                    source='crm',
                    delivery_date=row['delivery_date'],
                    customer_name=row['customer_name'],
                    amount_collected=amount_collected,
                    raw_data=row['raw_data']
                )
                self.db.add(delivery)
                if not order_id:
                    logger.warning(
                        "Delivery for %s has no matching Order", row['order_number']
                    )

    def _parse_date(self, date_str: Any) -> Optional[Any]:
        if date_str is None or (isinstance(date_str, float) and pd.isna(date_str)) or str(date_str).strip() == '':
            return None
        try:
            return parse(str(date_str)).date()
        except Exception:
            return None

    def _parse_int(self, val: Any) -> int:
        try:
            return int(float(str(val).strip()))
        except (ValueError, TypeError):
            return 0

    def _parse_float(self, val: Any) -> float:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return 0.0
        try:
            return float(str(val).strip())
        except (ValueError, TypeError):
            return 0.0
