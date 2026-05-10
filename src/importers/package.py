"""
Package Sales & Recharge importer.

Parses the CRM Package Sales report (Sales + Recharges) and optionally
enriches with customer details from the Package Insights report.
Infers payment mode (Cash vs Online) by cross-referencing with MSWIPE
records on the same date.
"""

import logging
import pandas as pd
from datetime import date as date_type
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.importers.base import BaseImporter, read_excel_auto, sanitize_raw_data
from src.models.package_transaction import PackageTransaction
from src.models.payments import PaymentEvent

logger = logging.getLogger(__name__)


class PackageImporter(BaseImporter):
    """
    Imports package sales and recharge transactions.

    The sales file has columns:
        Staff | Package | Customer | Sale | Recharge | Sale/ Recharge On

    Each row is either a Sale (new package) or Recharge (wallet top-up).
    Both represent actual cash/MSWIPE inflows.
    """

    def __init__(self, db_session: Session):
        super().__init__(db_session)
        self.insights_lookup: Dict[str, Dict] = {}  # customer_name → insights

    def load_insights(self, insights_path: str) -> None:
        """Load package insights for customer enrichment (code, mobile)."""
        try:
            df = read_excel_auto(insights_path)
            for _, row in df.iterrows():
                name = str(row.get('Customer', '')).strip().upper()
                if name:
                    self.insights_lookup[name] = {
                        'customer_code': str(row.get('Customer Code', '')).strip(),
                        'mobile': str(row.get('Mobile', '')).strip(),
                        'balance': float(row.get('Balance', 0) or 0),
                    }
            logger.info("Loaded %d package insights records", len(self.insights_lookup))
        except Exception as e:
            logger.warning("Could not load insights file: %s", e)

    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        """Parse the package sales Excel file."""
        insights_path = kwargs.get('insights_path')
        if insights_path:
            self.load_insights(insights_path)

        df = read_excel_auto(file_path)
        logger.info("Read %d rows from package sales file", len(df))

        records = []
        for _, row in df.iterrows():
            raw = sanitize_raw_data(row.to_dict())
            sale_amt = float(row.get('Sale', 0) or 0)
            recharge_amt = float(row.get('Recharge', 0) or 0)
            date_val = row.get('Sale/ Recharge On')
            customer = str(row.get('Customer', '')).strip()
            package = str(row.get('Package', '')).strip()
            staff = str(row.get('Staff', '')).strip()

            if sale_amt > 0:
                records.append({
                    'customer_name': customer,
                    'package_name': package,
                    'transaction_type': 'Sale',
                    'amount': sale_amt,
                    'transaction_date': date_val,
                    'staff': staff,
                    'raw_data': raw,
                })
            if recharge_amt > 0:
                records.append({
                    'customer_name': customer,
                    'package_name': package,
                    'transaction_type': 'Recharge',
                    'amount': recharge_amt,
                    'transaction_date': date_val,
                    'staff': staff,
                    'raw_data': raw,
                })

        return records

    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize dates and customer names."""
        normalized = []
        for rec in raw_data:
            # Parse date
            dt = rec['transaction_date']
            if dt is None:
                self.errors.append({'row': rec, 'error': 'Missing date'})
                continue
            if hasattr(dt, 'date'):
                dt = dt.date()
            elif isinstance(dt, str):
                try:
                    from dateutil.parser import parse
                    dt = parse(dt).date()
                except Exception:
                    self.errors.append({'row': rec, 'error': f'Invalid date: {dt}'})
                    continue

            rec['transaction_date'] = dt
            rec['customer_name'] = rec['customer_name'].strip()

            # Enrich from insights
            lookup_key = rec['customer_name'].upper()
            if lookup_key in self.insights_lookup:
                info = self.insights_lookup[lookup_key]
                rec['customer_code'] = info.get('customer_code', '')
                rec['mobile'] = info.get('mobile', '')
            else:
                rec['customer_code'] = ''
                rec['mobile'] = ''

            normalized.append(rec)

        return normalized

    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate amounts and required fields."""
        valid = []
        for rec in data:
            if rec['amount'] <= 0:
                self.errors.append({'row': rec, 'error': 'Amount must be positive'})
                continue
            if not rec['customer_name']:
                self.errors.append({'row': rec, 'error': 'Missing customer name'})
                continue
            valid.append(rec)
        return valid

    def _infer_payment_modes(self, data: List[Dict[str, Any]]) -> None:
        """
        Infer whether each package was paid via Cash or Online (MSWIPE).

        For each transaction date+amount, check if MSWIPE has a matching
        payment. If yes → Online. If no → Cash.
        """
        # Load all MSWIPE payments indexed by (date, amount)
        mswipe_payments = self.db.query(PaymentEvent).filter(
            PaymentEvent.source == 'mswipe',
        ).all()

        # Build a multiset: (date, amount) → count of available matches
        mswipe_index: Dict[tuple, int] = {}
        for p in mswipe_payments:
            key = (p.payment_date, float(p.amount))
            mswipe_index[key] = mswipe_index.get(key, 0) + 1

        cash_count = 0
        online_count = 0
        for rec in data:
            key = (rec['transaction_date'], rec['amount'])
            if mswipe_index.get(key, 0) > 0:
                rec['payment_mode'] = 'Online'
                mswipe_index[key] -= 1
                online_count += 1
            else:
                rec['payment_mode'] = 'Cash'
                cash_count += 1

        logger.info(
            "Payment mode inference: %d Cash, %d Online (MSWIPE match)",
            cash_count, online_count
        )

    def save(self, data: List[Dict[str, Any]]) -> None:
        """Save package transactions to database (clear + insert)."""
        # Infer payment modes before saving
        self._infer_payment_modes(data)

        # Get date range for clearing
        dates = [rec['transaction_date'] for rec in data]
        min_date = min(dates)
        max_date = max(dates)

        # Clear existing records in the date range
        deleted = self.db.query(PackageTransaction).filter(
            PackageTransaction.transaction_date.between(min_date, max_date),
        ).delete(synchronize_session='fetch')
        if deleted:
            logger.info("Cleared %d existing package transactions (%s to %s)",
                        deleted, min_date, max_date)

        # Insert new records
        for rec in data:
            txn = PackageTransaction(
                customer_name=rec['customer_name'],
                customer_code=rec.get('customer_code', ''),
                mobile=rec.get('mobile', ''),
                package_name=rec['package_name'],
                transaction_type=rec['transaction_type'],
                amount=rec['amount'],
                transaction_date=rec['transaction_date'],
                payment_mode=rec.get('payment_mode', 'Cash'),
                staff=rec.get('staff', ''),
                raw_data=rec.get('raw_data'),
            )
            self.db.add(txn)

        logger.info("Saved %d package transactions", len(data))
