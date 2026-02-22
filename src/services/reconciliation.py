from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import date
from typing import List, Dict, Any, Optional
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException
from src.models.cash_register import CashRegisterEntry

class ReconciliationService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.amount_tolerance = 2.0
        self.credit_tolerance = 1.0
        self.cash_variance_tolerance = 100.0

    def run_reconciliation(self, run_date: date) -> ReconciliationRun:
        # Create run record
        # Check if run exists?
        run = self.db.query(ReconciliationRun).filter_by(run_date=run_date).first()
        if not run:
            run = ReconciliationRun(run_date=run_date, status='pending')
            self.db.add(run)
        else:
            run.status = 'pending' # Reset status
            # Clear existing exceptions for this run?
            self.db.query(OrderException).filter_by(reconciliation_run_id=run.id).delete()

        self.db.commit()

        try:
            # 2. Check Order-level rules
            self._check_order_rules(run_date, run.id)

            # 3. Check Day-level rules (GPay, Cash)
            self._check_day_rules(run_date, run.id)

            run.status = 'complete'
            run.completed_at = func.now()
            self.db.commit()
            return run
        except Exception as e:
            run.status = 'failed'
            self.db.commit()
            raise e

    def _check_order_rules(self, run_date: date, run_id: int):
        # Iterate over orders relevant to this date.
        order_ids = set()

        # Notepad Deliveries on run_date
        deliveries = self.db.query(DeliveryEvent).filter(DeliveryEvent.delivery_date == run_date).all()
        for d in deliveries:
            if d.order_id:
                order_ids.add(d.order_id)

        # Payments on run_date
        payments = self.db.query(PaymentEvent).filter(PaymentEvent.payment_date == run_date).all()
        for p in payments:
            if p.order_id:
                order_ids.add(p.order_id)

        for order_id in order_ids:
            order = self.db.get(Order, order_id)
            if not order:
                continue

            self._reconcile_order(order, run_date, run_id)

    def _reconcile_order(self, order: Order, run_date: date, run_id: int):
        # Calculate Ledger
        # order.payments relationship
        total_paid = sum(p.amount for p in order.payments)
        balance_due = float(order.order_amount) - float(total_paid)

        # Delivery Status Logic
        notepad_delivery = next((d for d in order.deliveries if d.source == 'notepad'), None)

        # Since I didn't implement DeliveryEvent(source='crm') in CRMImporter yet,
        # I rely on order.raw_data.get('Delivery Date')
        crm_delivery_date = None
        if order.raw_data and order.raw_data.get('Delivery Date'):
            # It might be a string, need parsing?
            # Assuming normalize parsed it but stored in raw_data as original?
            # normalize stored parsed date in `delivery_date` key of normalized dict, but that key was not on Order model.
            # So raw_data has original string.
            # But wait, `CRMImporter.normalize` parses it.
            # And `CRMImporter.save` currently ignores it except putting in raw_data.
            pass

        # Assuming we can infer delivery from CRM if `Delivery Date` column is present in raw_data and not empty
        is_delivered_crm = False
        if order.raw_data:
            d_date = order.raw_data.get('Delivery Date')
            if d_date and str(d_date).lower() not in ['none', 'nan', '']:
                is_delivered_crm = True

        is_delivered_notepad = notepad_delivery is not None

        # Flag: Delivered in Notepad but not CRM
        if is_delivered_notepad and not is_delivered_crm:
             self._create_exception(
                 run_id, order.id, 'high', 'DeliveredNotMarkedCRM', ['MissingCRM'],
                 {'notepad_date': str(notepad_delivery.delivery_date)}, 'Mark as delivered in CRM'
             )

        # Flag: Delivered in CRM but not Notepad
        # Only check if CRM says delivered ON run_date? Or generic check?
        # If we are reconciling run_date, maybe we only care if CRM says delivered TODAY but no notepad entry?
        if is_delivered_crm and not is_delivered_notepad:
             # Check if CRM delivery date matches run_date?
             # Since we don't have easy access to parsed CRM delivery date without re-parsing,
             # we skip strict date check or try to parse.
             self._create_exception(
                 run_id, order.id, 'medium', 'DeliveredMissingNotepad', ['MissingNotepad'],
                 {'crm_raw_date': str(order.raw_data.get('Delivery Date'))}, 'Check runner notepad'
             )

        # Payment Logic
        if is_delivered_notepad and notepad_delivery.delivery_date == run_date:
            # Credit Policy Violation
            # If balance > tolerance
            if balance_due > self.credit_tolerance:
                 self._create_exception(
                     run_id, order.id, 'high', 'CreditPolicyViolation', ['UnpaidDelivery'],
                     {'balance': float(balance_due), 'threshold': self.credit_tolerance}, 'Collect payment'
                 )

    def _check_day_rules(self, run_date: date, run_id: int):
        # GPay Validation
        # Total CRM GPay vs Total MSWIPE GPay
        crm_gpay = self.db.query(func.sum(PaymentEvent.amount)).filter(
            PaymentEvent.source == 'crm',
            PaymentEvent.payment_mode == 'GPay',
            PaymentEvent.payment_date == run_date
        ).scalar() or 0.0

        mswipe_gpay = self.db.query(func.sum(PaymentEvent.amount)).filter(
            PaymentEvent.source == 'mswipe',
            PaymentEvent.payment_date == run_date
        ).scalar() or 0.0

        diff = float(crm_gpay) - float(mswipe_gpay)

        if abs(diff) > self.amount_tolerance:
            severity = 'high' if abs(diff) > 100 else 'medium'
            self._create_exception(
                run_id, None, severity, 'GPayMismatch', ['DayTotalMismatch'],
                {'crm_gpay': float(crm_gpay), 'mswipe_gpay': float(mswipe_gpay), 'diff': diff},
                'Investigate GPay discrepancy'
            )

        # Cash Validation
        expected_cash = self.db.query(func.sum(DeliveryEvent.amount_collected)).filter(
            DeliveryEvent.source == 'notepad',
            DeliveryEvent.payment_mode == 'Cash',
            DeliveryEvent.delivery_date == run_date
        ).scalar() or 0.0

        # Get Cash Register Derived Cash
        register_entry = self.db.query(CashRegisterEntry).filter(
            CashRegisterEntry.entry_date == run_date
        ).first()

        if register_entry:
            derived_cash = float(register_entry.derived_cash_from_orders or 0.0)
            cash_diff = derived_cash - float(expected_cash)

            if abs(cash_diff) > self.cash_variance_tolerance:
                 self._create_exception(
                     run_id, None, 'high', 'CashVariance', ['CashMismatch'],
                     {'expected': float(expected_cash), 'derived': derived_cash, 'diff': cash_diff},
                     'Check cash register'
                 )

    def _create_exception(self, run_id, order_id, severity, type, tags, evidence, action):
        ex = OrderException(
            reconciliation_run_id=run_id,
            order_id=order_id,
            severity=severity,
            exception_type=type,
            reason_tags=tags,
            evidence=evidence,
            suggested_action=action
        )
        self.db.add(ex)
