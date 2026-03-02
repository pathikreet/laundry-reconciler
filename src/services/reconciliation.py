import logging
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
from src.config.settings import Settings
from src.exceptions import ReconciliationError

logger = logging.getLogger(__name__)


class ReconciliationService:
    def __init__(self, db_session: Session, settings: Settings = None):
        self.db = db_session
        self.settings = settings or Settings()
        self.amount_tolerance = self.settings.amount_tolerance
        self.credit_tolerance = self.settings.credit_tolerance if hasattr(self.settings, 'credit_tolerance') else 1.0
        self.cash_variance_tolerance = self.settings.cash_variance_tolerance
        self.gpay_tolerance = self.settings.gpay_tolerance

    def run_reconciliation(self, run_date: date) -> ReconciliationRun:
        """
        Orchestrates the full reconciliation pipeline for a given date.

        Steps:
        1. Create/reset reconciliation run record
        2. Apply order-level rules (delivery status, credit policy)
        3. Apply day-level rules (GPay validation, cash variance)
        4. Update run status and summary statistics

        Args:
            run_date: The calendar date to reconcile.

        Returns:
            The completed ReconciliationRun record.

        Raises:
            ReconciliationError: If the reconciliation process fails.
        """
        run = self._initialize_run(run_date)

        try:
            # Apply rules
            order_exceptions = self._check_order_rules(run_date, run.id)
            late_exceptions = self._check_late_payments(run_date, run.id)
            day_exceptions = self._check_day_rules(run_date, run.id)

            # Update summary
            run.status = 'complete'
            run.completed_at = func.now()
            run.summary_stats = {
                'order_exceptions': order_exceptions,
                'late_payment_exceptions': late_exceptions,
                'day_exceptions': day_exceptions,
                'total_exceptions': order_exceptions + late_exceptions + day_exceptions,
            }
            self.db.commit()

            logger.info(
                "Reconciliation complete for %s: %d order exceptions, %d day exceptions",
                run_date, order_exceptions, day_exceptions
            )
            return run

        except Exception as e:
            run.status = 'failed'
            self.db.commit()
            logger.error("Reconciliation failed for %s: %s", run_date, str(e))
            raise ReconciliationError(
                f"Reconciliation failed for {run_date}: {e}",
                details={"run_date": str(run_date), "error": str(e)}
            )

    def run_reconciliation_range(self, start_date: date, end_date: date,
                                  progress_callback=None) -> Dict[str, Any]:
        """
        Run reconciliation for every day in a date range.

        Args:
            start_date: First date to reconcile (inclusive).
            end_date: Last date to reconcile (inclusive).
            progress_callback: Optional callable(current_day, total_days) for progress updates.

        Returns:
            Consolidated summary with totals and per-day breakdown.
        """
        from datetime import timedelta

        total_days = (end_date - start_date).days + 1
        results = []
        totals = {
            'order_exceptions': 0,
            'late_payment_exceptions': 0,
            'day_exceptions': 0,
            'total_exceptions': 0,
            'days_processed': 0,
            'days_with_exceptions': 0,
            'days_with_activity': 0,
        }

        current = start_date
        day_num = 0
        while current <= end_date:
            day_num += 1
            if progress_callback:
                progress_callback(day_num, total_days)

            try:
                run = self.run_reconciliation(current)
                stats = run.summary_stats or {}
                totals['days_processed'] += 1

                exc_count = stats.get('total_exceptions', 0)
                totals['order_exceptions'] += stats.get('order_exceptions', 0)
                totals['late_payment_exceptions'] += stats.get('late_payment_exceptions', 0)
                totals['day_exceptions'] += stats.get('day_exceptions', 0)
                totals['total_exceptions'] += exc_count

                if exc_count > 0:
                    totals['days_with_exceptions'] += 1

                # Check if day had any activity
                order_ids = self._get_order_ids_for_date(current)
                if order_ids:
                    totals['days_with_activity'] += 1

                results.append({
                    'date': current,
                    'run_id': run.id,
                    'exceptions': exc_count,
                    'status': 'complete',
                })

            except ReconciliationError as e:
                logger.warning("Reconciliation failed for %s: %s", current, e)
                results.append({
                    'date': current,
                    'run_id': None,
                    'exceptions': 0,
                    'status': 'failed',
                })

            current += timedelta(days=1)

        totals['per_day'] = results
        logger.info(
            "Range reconciliation %s to %s: %d days, %d total exceptions",
            start_date, end_date, totals['days_processed'], totals['total_exceptions']
        )
        return totals

    # ── Initialization ────────────────────────────────────────

    def _initialize_run(self, run_date: date) -> ReconciliationRun:
        """Create or reset a reconciliation run for the given date."""
        run = self.db.query(ReconciliationRun).filter_by(run_date=run_date).first()
        if not run:
            run = ReconciliationRun(run_date=run_date, status='pending')
            self.db.add(run)
        else:
            run.status = 'pending'
            self.db.query(OrderException).filter_by(reconciliation_run_id=run.id).delete()

        self.db.commit()
        return run

    # ── Order-Level Rules ─────────────────────────────────────

    def _check_order_rules(self, run_date: date, run_id: int) -> int:
        """
        Apply order-level reconciliation rules.

        Rules:
        1. Delivery status mismatch (CRM vs Notepad)
        2. Credit policy violation (unpaid deliveries)

        Returns:
            Count of exceptions created.
        """
        exception_count = 0
        order_ids = self._get_order_ids_for_date(run_date)

        for order_id in order_ids:
            order = self.db.get(Order, order_id)
            if not order:
                continue
            exception_count += self._check_delivery_status(order, run_date, run_id)
            exception_count += self._check_credit_policy(order, run_date, run_id)
            exception_count += self._check_notepad_amount_mismatch(order, run_date, run_id)

        return exception_count

    # ── Late Payment Detection ────────────────────────────────

    def _check_late_payments(self, run_date: date, run_id: int) -> int:
        """
        Flag payments made after delivery date.

        For each order with a CRM delivery event on run_date, checks if
        any payment was made ≥ threshold days after delivery.
        """
        count = 0
        threshold = getattr(self.settings, 'late_payment_threshold_days', 0)

        # Get deliveries on this date
        deliveries = self.db.query(DeliveryEvent).filter(
            DeliveryEvent.delivery_date == run_date,
            DeliveryEvent.source == 'crm'
        ).all()

        for delivery in deliveries:
            if not delivery.order_id:
                continue

            # Check all payments for this order
            payments = self.db.query(PaymentEvent).filter(
                PaymentEvent.order_id == delivery.order_id
            ).all()

            for payment in payments:
                if not payment.payment_date:
                    continue

                days_late = (payment.payment_date - delivery.delivery_date).days
                if days_late > threshold:
                    self._create_exception(
                        run_id, delivery.order_id, 'medium', 'LatePayment',
                        reason_tags=['late_payment'],
                        evidence={
                            'delivery_date': str(delivery.delivery_date),
                            'payment_date': str(payment.payment_date),
                            'days_late': days_late,
                            'amount': float(payment.amount),
                            'payment_mode': payment.payment_mode,
                        },
                        suggested_action=f'Review: payment of ₹{float(payment.amount)} received {days_late} days after delivery',
                    )
                    count += 1
                    logger.info(
                        "Late payment flagged: order_id=%d, %d days late, ₹%.2f",
                        delivery.order_id, days_late, float(payment.amount)
                    )

        return count

    def _get_order_ids_for_date(self, run_date: date) -> set:
        """Collect all order IDs that have activity on the given date."""
        order_ids = set()

        deliveries = self.db.query(DeliveryEvent).filter(
            DeliveryEvent.delivery_date == run_date
        ).all()
        for d in deliveries:
            if d.order_id:
                order_ids.add(d.order_id)

        payments = self.db.query(PaymentEvent).filter(
            PaymentEvent.payment_date == run_date
        ).all()
        for p in payments:
            if p.order_id:
                order_ids.add(p.order_id)

        return order_ids

    def _check_delivery_status(self, order: Order, run_date: date, run_id: int) -> int:
        """
        Check for delivery status mismatches between CRM and Notepad.

        Flags:
        - Delivered in Notepad but NOT in CRM Delivery Report → high severity
        - Delivered in CRM but missing from Notepad → medium severity

        CRM delivery is confirmed by the presence of a DeliveryEvent with source='crm',
        created by the CRM Delivery importer. Do NOT use raw_data fields which are from
        the Sales report and may not contain delivery info.
        """
        count = 0
        notepad_delivery = next((d for d in order.deliveries if d.source == 'notepad'), None)
        crm_delivery = next((d for d in order.deliveries if d.source == 'crm'), None)

        is_delivered_crm = crm_delivery is not None
        is_delivered_notepad = notepad_delivery is not None

        if is_delivered_notepad and not is_delivered_crm:
            self._create_exception(
                run_id, order.id, 'high', 'DeliveredNotMarkedCRM',
                ['MissingCRM'],
                {'notepad_date': str(notepad_delivery.delivery_date)},
                'Mark as delivered in CRM'
            )
            count += 1

        if is_delivered_crm and not is_delivered_notepad:
            self._create_exception(
                run_id, order.id, 'medium', 'DeliveredMissingNotepad',
                ['MissingNotepad'],
                {'crm_date': str(crm_delivery.delivery_date)},
                'Check runner notepad'
            )
            count += 1

        return count

    def _check_credit_policy(self, order: Order, run_date: date, run_id: int) -> int:
        """
        Check for credit policy violations (unpaid deliveries).

        A violation occurs when an order is delivered but the outstanding
        balance exceeds the credit tolerance threshold.
        """
        notepad_delivery = next((d for d in order.deliveries if d.source == 'notepad'), None)
        if not notepad_delivery or notepad_delivery.delivery_date != run_date:
            return 0

        total_paid = sum(float(p.amount) for p in order.payments)
        balance_due = float(order.order_amount) - total_paid

        if balance_due > self.credit_tolerance:
            self._create_exception(
                run_id, order.id, 'high', 'CreditPolicyViolation',
                ['UnpaidDelivery'],
                {'balance': round(balance_due, 2), 'threshold': self.credit_tolerance},
                'Collect payment'
            )
            return 1
        return 0

    # ── Notepad Amount Mismatch Detection ──────────────────────

    def _check_notepad_amount_mismatch(self, order: Order, run_date: date, run_id: int) -> int:
        """
        Check if notepad-recorded amount differs from CRM payment amount.

        Notepad amounts are entered manually by runners/staff and may be
        unreliable. CRM amounts are always the trusted source. If there's
        a mismatch beyond amount_tolerance, flag it for review.
        """
        # Get notepad deliveries for this order on run_date
        notepad_deliveries = [
            d for d in order.deliveries
            if d.source == 'notepad' and d.delivery_date == run_date
        ]
        if not notepad_deliveries:
            return 0

        notepad_total = sum(float(d.amount_collected or 0) for d in notepad_deliveries)

        # Get CRM payment total for this order
        crm_payments = [p for p in order.payments if p.source == 'crm']
        if not crm_payments:
            return 0  # No CRM data to compare against

        crm_total = sum(float(p.amount) for p in crm_payments)

        variance = abs(notepad_total - crm_total)
        if variance > self.amount_tolerance:
            self._create_exception(
                run_id, order.id, 'medium', 'NotepadAmountMismatch',
                ['NotepadVsCRM', 'ManualEntryVariance'],
                {
                    'notepad_amount': round(notepad_total, 2),
                    'crm_amount': round(crm_total, 2),
                    'variance': round(variance, 2),
                    'trusted_source': 'CRM',
                },
                'Review notepad entry — CRM amount is authoritative'
            )
            logger.info(
                "Notepad mismatch for %s: notepad=%.2f vs CRM=%.2f (var=%.2f)",
                order.order_number, notepad_total, crm_total, variance
            )
            return 1
        return 0

    # ── Day-Level Rules ───────────────────────────────────────

    def _check_day_rules(self, run_date: date, run_id: int) -> int:
        """
        Apply day-level reconciliation rules.

        Rules:
        1. GPay day-total validation (CRM vs MSWIPE)
        2. Cash variance validation (Notepad vs Cash Register)

        Returns:
            Count of exceptions created.
        """
        count = 0
        count += self._check_gpay_totals(run_date, run_id)
        count += self._check_cash_variance(run_date, run_id)
        return count

    def _check_gpay_totals(self, run_date: date, run_id: int) -> int:
        """
        Validate GPay day totals: CRM GPay total vs MSWIPE total.

        Uses configurable gpay_tolerance for the threshold.
        """
        crm_gpay = self.db.query(func.sum(PaymentEvent.amount)).filter(
            PaymentEvent.source == 'crm',
            PaymentEvent.payment_mode.in_(['GPay', 'Google Pay', 'UPI']),
            PaymentEvent.payment_date == run_date
        ).scalar() or 0.0

        mswipe_gpay = self.db.query(func.sum(PaymentEvent.amount)).filter(
            PaymentEvent.source == 'mswipe',
            PaymentEvent.payment_date == run_date
        ).scalar() or 0.0

        diff = float(crm_gpay) - float(mswipe_gpay)

        if abs(diff) > self.gpay_tolerance:
            severity = 'high' if abs(diff) > 100 else 'medium'
            self._create_exception(
                run_id, None, severity, 'GPayMismatch',
                ['DayTotalMismatch'],
                {
                    'crm_gpay': round(float(crm_gpay), 2),
                    'mswipe_gpay': round(float(mswipe_gpay), 2),
                    'diff': round(diff, 2)
                },
                'Investigate GPay discrepancy'
            )
            return 1
        return 0

    def _check_cash_variance(self, run_date: date, run_id: int) -> int:
        """
        Validate cash: expected cash (Notepad) vs derived cash (Cash Register).

        Uses configurable cash_variance_tolerance for the threshold.
        """
        expected_cash = self.db.query(func.sum(DeliveryEvent.amount_collected)).filter(
            DeliveryEvent.source == 'notepad',
            DeliveryEvent.payment_mode == 'Cash',
            DeliveryEvent.delivery_date == run_date
        ).scalar() or 0.0

        register_entry = self.db.query(CashRegisterEntry).filter(
            CashRegisterEntry.entry_date == run_date
        ).first()

        if register_entry:
            derived_cash = float(register_entry.derived_cash_from_orders or 0.0)
            cash_diff = derived_cash - float(expected_cash)

            if abs(cash_diff) > self.cash_variance_tolerance:
                self._create_exception(
                    run_id, None, 'high', 'CashVariance',
                    ['CashMismatch'],
                    {
                        'expected': round(float(expected_cash), 2),
                        'derived': round(derived_cash, 2),
                        'diff': round(cash_diff, 2)
                    },
                    'Check cash register'
                )
                return 1
        return 0

    # ── Helpers ────────────────────────────────────────────────

    def _create_exception(self, run_id, order_id, severity, exc_type, tags, evidence, action):
        """Create and persist a reconciliation exception."""
        ex = OrderException(
            reconciliation_run_id=run_id,
            order_id=order_id,
            severity=severity,
            exception_type=exc_type,
            reason_tags=tags,
            evidence=evidence,
            suggested_action=action
        )
        self.db.add(ex)
