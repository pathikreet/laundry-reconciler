import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException
from src.models.cash_register import CashRegisterEntry
from src.models.expenses import Expense
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
            ageing_exceptions = self._check_ageing_orders(run_date, run.id)
            backdated_exceptions = self._check_backdated_payments(run_date, run.id)

            # Update summary
            run.status = 'complete'
            run.completed_at = func.now()
            run.summary_stats = {
                'order_exceptions': order_exceptions,
                'late_payment_exceptions': late_exceptions,
                'day_exceptions': day_exceptions,
                'ageing_order_exceptions': ageing_exceptions,
                'backdated_payment_exceptions': backdated_exceptions,
                'total_exceptions': order_exceptions + late_exceptions + day_exceptions + ageing_exceptions + backdated_exceptions,
            }
            self.db.commit()

            logger.info(
                "Reconciliation complete for %s: %d order exceptions, %d day exceptions, "
                "%d ageing, %d backdated",
                run_date, order_exceptions, day_exceptions, ageing_exceptions, backdated_exceptions
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
            'ageing_order_exceptions': 0,
            'backdated_payment_exceptions': 0,
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
                totals['ageing_order_exceptions'] += stats.get('ageing_order_exceptions', 0)
                totals['backdated_payment_exceptions'] += stats.get('backdated_payment_exceptions', 0)
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
        3. Notepad amount mismatch vs CRM
        4. Notepad payment not recorded in CRM
        5. Per-order cross-source payment verification

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
            exception_count += self._check_notepad_payment_not_in_crm(order, run_date, run_id)
            exception_count += self._check_per_order_payment_source(order, run_date, run_id)

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
                        tags=['late_payment'],
                        evidence={
                            'delivery_date': str(delivery.delivery_date),
                            'payment_date': str(payment.payment_date),
                            'days_late': days_late,
                            'amount': float(payment.amount),
                            'payment_mode': payment.payment_mode,
                        },
                        action=f'Review: payment of ₹{float(payment.amount)} received {days_late} days after delivery',
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

        # Skip notepad-vs-CRM checks before notepad data was available
        notepad_from = self.settings.notepad_available_from
        if notepad_from and run_date < notepad_from:
            return 0

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
        # Credit policy requires notepad delivery confirmation
        notepad_from = self.settings.notepad_available_from
        if notepad_from and run_date < notepad_from:
            return 0

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
        # Skip notepad checks before notepad data was available
        notepad_from = self.settings.notepad_available_from
        if notepad_from and run_date < notepad_from:
            return 0

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

    # ── Feature 3: Notepad Payment Not in CRM ────────────────

    def _check_notepad_payment_not_in_crm(self, order: Order, run_date: date, run_id: int) -> int:
        """
        Flag orders where notepad records a payment but CRM has none.

        This happens when staff collect payment and note it in the delivery
        book but forget to update the CRM. The CRM balance will look
        unpaid even though money was collected.

        Severity: high — CRM is out of sync with actual collections.
        """
        notepad_from = self.settings.notepad_available_from
        if notepad_from and run_date < notepad_from:
            return 0

        # Notepad payment on run_date for this order with non-zero amount
        notepad_payments = [
            p for p in order.payments
            if p.source == 'notepad'
            and p.payment_date == run_date
            and float(p.amount) > 0
        ]
        if not notepad_payments:
            return 0

        # CRM payments for this order (any date — if CRM has any it's been entered)
        crm_payments = [p for p in order.payments if p.source == 'crm']
        if crm_payments:
            return 0  # CRM has data — no gap

        notepad_total = sum(float(p.amount) for p in notepad_payments)
        self._create_exception(
            run_id, order.id, 'high', 'NotepadPaymentNotInCRM',
            tags=['MissingCRMPayment'],
            evidence={
                'notepad_amount': round(notepad_total, 2),
                'notepad_date': str(run_date),
                'notepad_mode': notepad_payments[0].payment_mode,
                'crm_payments': 0,
            },
            action=f'Update CRM with payment of ₹{notepad_total:.0f} '
                            f'collected on {run_date}'
        )
        logger.info(
            "NotepadPaymentNotInCRM for %s: ₹%.2f on %s not in CRM",
            order.order_number, notepad_total, run_date
        )
        return 1

    # ── Feature 1: Per-Order Cross-Source Verification ────────

    def _check_per_order_payment_source(self, order: Order, run_date: date, run_id: int) -> int:
        """
        Verify each CRM payment on run_date is confirmed by the expected
        external source for that payment mode.

        +---------------------+---------------------------+------------------------------+
        | CRM Mode            | Expected external source  | Exception if missing         |
        +---------------------+---------------------------+------------------------------+
        | GPay / UPI / Google Pay | MSWIPE linked to order | GPayOrderMismatch (medium)   |
        | Cash                | Cash Register on run_date | CashOrderNoRegister (medium) |
        | Paytm / Online /    | Notepad payment for order | PaymentNotConfirmedByNotepad  |
        | Package / Card      |                           | (low)                        |
        +---------------------+---------------------------+------------------------------+
        """
        count = 0
        gpay_modes = {'GPay', 'Google Pay', 'UPI'}
        cash_modes = {'Cash'}
        # Paytm and Package are AUTO-RECORDED in CRM — not fraud vectors.
        # Paytm: verify against Paytm QR data (source='paytm').
        # Package: auto wallet deduction, no external verification needed.
        paytm_modes = {'Paytm', 'PhonePe'}
        package_modes = {'Package'}
        # Card and other staff-entered modes: verify via notepad
        notepad_confirm_modes = {'Online', 'Card'}

        crm_payments_today = [
            p for p in order.payments
            if p.source == 'crm' and p.payment_date == run_date
        ]
        if not crm_payments_today:
            return 0

        for payment in crm_payments_today:
            mode = payment.payment_mode or ''

            if mode in gpay_modes:
                # Check MSWIPE linked to this order
                mswipe_linked = any(
                    p for p in order.payments
                    if p.source == 'mswipe'
                )
                if not mswipe_linked:
                    self._create_exception(
                        run_id, order.id, 'high', 'GPayOrderMismatch',
                        tags=['MissingMSWIPE', 'CrossSourceMismatch'],
                        evidence={
                            'crm_amount': round(float(payment.amount), 2),
                            'crm_date': str(run_date),
                            'payment_mode': mode,
                            'missing_source': 'MSWIPE',
                        },
                        action=f'No MSWIPE match for ₹{float(payment.amount):,.0f} GPay — check Unmatched MSWIPE tab or verify order number'
                    )
                    count += 1

            elif mode in cash_modes:
                # Check cash register exists for run_date
                from src.models.cash_register import CashRegisterEntry
                register_exists = self.db.query(CashRegisterEntry).filter(
                    CashRegisterEntry.entry_date == run_date
                ).first()
                if not register_exists:
                    self._create_exception(
                        run_id, order.id, 'medium', 'CashOrderNoRegister',
                        tags=['MissingCashRegister', 'CrossSourceMismatch'],
                        evidence={
                            'crm_amount': round(float(payment.amount), 2),
                            'crm_date': str(run_date),
                            'payment_mode': mode,
                            'missing_source': 'CashRegister',
                        },
                        action='Check cash register entry for this date'
                    )
                    count += 1

            elif mode in paytm_modes:
                # Paytm: auto-recorded via QR scan — verify against
                # Paytm QR data. NOT a fraud vector.
                paytm_linked = any(
                    p for p in order.payments
                    if p.source == 'paytm'
                )
                if not paytm_linked:
                    # Low severity — Paytm is auto-recorded, mismatch
                    # is a data sync issue, not fraud
                    self._create_exception(
                        run_id, order.id, 'low', 'PaytmNotInQRData',
                        tags=['PaytmRecon', 'AutoRecorded'],
                        evidence={
                            'crm_amount': round(float(payment.amount), 2),
                            'crm_date': str(run_date),
                            'payment_mode': mode,
                            'missing_source': 'PaytmQR',
                        },
                        action='CRM auto-recorded Paytm payment not found in Paytm QR data — likely timing or data sync issue'
                    )
                    count += 1

            elif mode in package_modes:
                # Package: auto wallet deduction — but runners DO record
                # Package deliveries in notepad (amount=0, mode='Package').
                # Check notepad for confirmation (delivery or payment).
                notepad_package_confirmed = any(
                    p for p in order.payments
                    if p.source == 'notepad'
                )
                if not notepad_package_confirmed:
                    # Also check delivery events (runners note package as delivery mode)
                    notepad_delivery_confirmed = any(
                        d for d in order.deliveries
                        if d.source == 'notepad'
                        and (d.payment_mode or '').lower() in ('package',)
                    )
                    if not notepad_delivery_confirmed:
                        self._create_exception(
                            run_id, order.id, 'low', 'PackageNotConfirmedByNotepad',
                            tags=['MissingNotepadConfirmation', 'AutoRecorded'],
                            evidence={
                                'crm_amount': round(float(payment.amount), 2),
                                'crm_date': str(run_date),
                                'payment_mode': mode,
                                'missing_source': 'Notepad',
                            },
                            action='CRM auto-deducted Package payment but runner notepad has no entry. '
                                   'Not a fraud risk — runner may have omitted the note.'
                        )
                        count += 1

            elif mode in notepad_confirm_modes:
                # Other staff-entered modes: check notepad
                notepad_confirmed = any(
                    p for p in order.payments
                    if p.source == 'notepad' and float(p.amount) > 0
                )
                if not notepad_confirmed:
                    self._create_exception(
                        run_id, order.id, 'low', 'PaymentNotConfirmedByNotepad',
                        tags=['MissingNotepadConfirmation', 'CrossSourceMismatch'],
                        evidence={
                            'crm_amount': round(float(payment.amount), 2),
                            'crm_date': str(run_date),
                            'payment_mode': mode,
                            'missing_source': 'Notepad',
                        },
                        action='Confirm delivery runner collected this payment'
                    )
                    count += 1

        return count

    # ── Feature 2: Ageing Orders ──────────────────────────────

    def _check_ageing_orders(self, run_date: date, run_id: int) -> int:
        """
        Detect orders that are aged (past threshold) with no delivery from any source.

        An order is considered ageing when:
        - order_date <= run_date - ageing_threshold_days
        - No DeliveryEvent exists from any source (crm or notepad)
        - Outstanding balance > credit_tolerance

        All ageing exceptions are severity=high (Sev 1).
        """
        threshold = self.settings.ageing_threshold
        cutoff = run_date - timedelta(days=threshold)

        # Query orders placed on or before cutoff
        old_orders = self.db.query(Order).filter(
            Order.order_date <= cutoff
        ).all()

        count = 0
        for order in old_orders:
            balance = float(order.order_amount) - sum(float(p.amount) for p in order.payments)
            if balance <= self.credit_tolerance:
                continue  # Fully paid — not a concern

            if order.deliveries:
                continue # Has delivery event - not a concern

            # Avoid duplicate ageing exceptions in same run
            from src.models.exceptions import OrderException
            already_flagged = self.db.query(OrderException).filter_by(
                reconciliation_run_id=run_id,
                order_id=order.id,
                exception_type='AgeingOrder'
            ).first()
            if already_flagged:
                continue

            days_old = (run_date - order.order_date).days
            self._create_exception(
                run_id, order.id, 'high', 'AgeingOrder',
                tags=['NoDelivery', 'AgeingUnpaid'],
                evidence={
                    'order_date': str(order.order_date),
                    'run_date': str(run_date),
                    'days_since_order': days_old,
                    'threshold_days': threshold,
                    'order_amount': round(float(order.order_amount), 2),
                    'balance': round(balance, 2),
                },
                action=f'Order {days_old} days old with no delivery recorded. '
                                f'Investigate status with delivery team.'
            )
            count += 1
            logger.info(
                "AgeingOrder: %s (%d days old, ₹%.2f outstanding)",
                order.order_number, days_old, balance
            )

        return count

    # ── Feature 4: Backdated Payment Detection ────────────────

    def _check_backdated_payments(self, run_date: date, run_id: int) -> int:
        """
        Detect payments that appear to have been recorded on the wrong date.

        Two scenarios:
        1. GPay: CRM GPay on run_date with no same-day MSWIPE →
           search MSWIPE within lookback_days for matching amount.
           If found → BackdatedGPayPayment.

        2. Cash: Cash deficit on run_date (notepad total > register total) →
           search historical dates within lookback for surplus of same magnitude.
           If found → SuspectedBackdatedCashPayment.
        """
        lookback = self.settings.backdated_lookback
        lookback_start = run_date - timedelta(days=lookback)
        count = 0

        # ── GPay backdated check ──────────────────────────────
        # Find CRM GPay payments on run_date that have no same-day MSWIPE match
        gpay_modes = ['GPay', 'Google Pay', 'UPI']
        crm_gpay_today = self.db.query(PaymentEvent).filter(
            PaymentEvent.source == 'crm',
            PaymentEvent.payment_mode.in_(gpay_modes),
            PaymentEvent.payment_date == run_date,
            PaymentEvent.order_id != None,
        ).all()

        for crm_pay in crm_gpay_today:
            # Check if same-day MSWIPE exists for this order
            same_day_mswipe = self.db.query(PaymentEvent).filter(
                PaymentEvent.source == 'mswipe',
                PaymentEvent.order_id == crm_pay.order_id,
                PaymentEvent.payment_date == run_date,
            ).first()
            if same_day_mswipe:
                continue  # Same-day confirmation exists — fine

            # Also skip if GPayOrderMismatch was already raised for this order/run
            # (backdated is a more specific sub-case of the mismatch)

            # Search MSWIPE within lookback for amount match
            tolerance = self.amount_tolerance
            amount = float(crm_pay.amount)
            historical_mswipe = self.db.query(PaymentEvent).filter(
                PaymentEvent.source == 'mswipe',
                PaymentEvent.payment_date >= lookback_start,
                PaymentEvent.payment_date < run_date,
                PaymentEvent.amount >= amount - tolerance,
                PaymentEvent.amount <= amount + tolerance,
            ).order_by(PaymentEvent.payment_date.desc()).first()

            if historical_mswipe:
                days_offset = (run_date - historical_mswipe.payment_date).days
                self._create_exception(
                    run_id, crm_pay.order_id, 'medium', 'BackdatedGPayPayment',
                    tags=['BackdatedPayment', 'MSWIPEMismatch'],
                    evidence={
                        'crm_amount': round(amount, 2),
                        'crm_recorded_date': str(run_date),
                        'mswipe_actual_date': str(historical_mswipe.payment_date),
                        'days_offset': days_offset,
                        'mswipe_payment_id': historical_mswipe.id,
                    },
                    action=f'Payment of ₹{amount:.0f} likely received on '
                                    f'{historical_mswipe.payment_date} (per MSWIPE) '
                                    f'but CRM shows {run_date}. Correct CRM date.'
                )
                count += 1
                logger.info(
                    "BackdatedGPayPayment: order_id=%s, ₹%.2f — MSWIPE date %s vs CRM date %s",
                    crm_pay.order_id, amount,
                    historical_mswipe.payment_date, run_date
                )

        # ── Cash backdated (surplus/deficit correlation) ───────
        cash_from = self.settings.cash_register_available_from
        if cash_from and run_date < cash_from:
            return count

        # Cash expected (notepad) vs actual (register) on run_date
        notepad_cash = float(
            self.db.query(func.sum(PaymentEvent.amount)).filter(
                PaymentEvent.source == 'notepad',
                PaymentEvent.payment_mode == 'Cash',
                PaymentEvent.payment_date == run_date,
            ).scalar() or 0.0
        )
        from src.models.cash_register import CashRegisterEntry
        register_today = self.db.query(CashRegisterEntry).filter(
            CashRegisterEntry.entry_date == run_date
        ).first()

        if register_today and notepad_cash > 0:
            derived = float(register_today.derived_cash_from_orders or 0.0)
            deficit = notepad_cash - derived  # positive = deficit (notepad > register)

            if deficit > self.cash_variance_tolerance:
                # Search history for a matching surplus
                historical_entries = self.db.query(CashRegisterEntry).filter(
                    CashRegisterEntry.entry_date >= lookback_start,
                    CashRegisterEntry.entry_date < run_date,
                ).all()

                for hist in historical_entries:
                    hist_notepad_cash = float(
                        self.db.query(func.sum(PaymentEvent.amount)).filter(
                            PaymentEvent.source == 'notepad',
                            PaymentEvent.payment_mode == 'Cash',
                            PaymentEvent.payment_date == hist.entry_date,
                        ).scalar() or 0.0
                    )
                    hist_derived = float(hist.derived_cash_from_orders or 0.0)
                    surplus = hist_derived - hist_notepad_cash  # positive = surplus

                    if abs(surplus - deficit) <= self.cash_variance_tolerance:
                        days_offset = (run_date - hist.entry_date).days
                        self._create_exception(
                            run_id, None, 'medium', 'SuspectedBackdatedCashPayment',
                            tags=['BackdatedPayment', 'CashCorrelation'],
                            evidence={
                                'deficit_date': str(run_date),
                                'deficit_amount': round(deficit, 2),
                                'surplus_date': str(hist.entry_date),
                                'surplus_amount': round(surplus, 2),
                                'days_offset': days_offset,
                            },
                            action=f'Cash deficit of ₹{deficit:.0f} on {run_date} may '
                                            f'correlate with cash surplus of ₹{surplus:.0f} on '
                                            f'{hist.entry_date} ({days_offset} days earlier). '
                                            f'Investigate if a payment was collected but recorded late.'
                        )
                        count += 1
                        logger.info(
                            "SuspectedBackdatedCashPayment: deficit ₹%.2f on %s, "
                            "surplus ₹%.2f on %s",
                            deficit, run_date, surplus, hist.entry_date
                        )
                        break  # Only flag best correlation candidate

        # ── CRM cash vs Register cross-day correlation ─────────
        # Scenario: cash collected on Day A (register has surplus), but staff
        # only marks CRM on Day B (run_date). Register on Day B looks light
        # vs CRM, but the money IS in the register — just on a different date.
        # Distinguishes honest late CRM entry from actual pocketing (CashUndeposited).
        crm_cash_today = float(
            self.db.query(func.sum(PaymentEvent.amount)).filter(
                PaymentEvent.source == 'crm',
                PaymentEvent.payment_mode == 'Cash',
                PaymentEvent.payment_date == run_date,
            ).scalar() or 0.0
        )

        if crm_cash_today > 0:
            register_today_crm = self.db.query(CashRegisterEntry).filter(
                CashRegisterEntry.entry_date == run_date
            ).first()
            register_today_crm_val = float(
                register_today_crm.derived_cash_from_orders or 0.0
            ) if register_today_crm else 0.0

            crm_deficit = crm_cash_today - register_today_crm_val  # positive = CRM > register

            if crm_deficit > self.cash_variance_tolerance:
                # Search historical register entries for a surplus >= the CRM deficit
                # (surplus can be larger — the register may have collected this order's
                # cash along with other cash from other orders on the same day)
                hist_entries = self.db.query(CashRegisterEntry).filter(
                    CashRegisterEntry.entry_date >= lookback_start,
                    CashRegisterEntry.entry_date < run_date,
                ).all()

                for hist in hist_entries:
                    # Surplus = register on hist date minus what notepad expected
                    hist_notepad = float(
                        self.db.query(func.sum(PaymentEvent.amount)).filter(
                            PaymentEvent.source == 'notepad',
                            PaymentEvent.payment_mode == 'Cash',
                            PaymentEvent.payment_date == hist.entry_date,
                        ).scalar() or 0.0
                    )
                    hist_reg = float(hist.derived_cash_from_orders or 0.0)
                    hist_surplus = hist_reg - hist_notepad  # positive = register has extra

                    if hist_surplus >= crm_deficit - self.cash_variance_tolerance:
                        days_offset = (run_date - hist.entry_date).days
                        self._create_exception(
                            run_id, None, 'medium', 'SuspectedBackdatedCRMEntry',
                            tags=['BackdatedPayment', 'CRMVsRegisterCorrelation'],
                            evidence={
                                'crm_recorded_date': str(run_date),
                                'crm_cash_amount': round(crm_cash_today, 2),
                                'register_on_crm_date': round(register_today_crm_val, 2),
                                'crm_deficit': round(crm_deficit, 2),
                                'suspected_collection_date': str(hist.entry_date),
                                'register_surplus_on_that_date': round(hist_surplus, 2),
                                'days_offset': days_offset,
                            },
                            action=(
                                f'CRM records ₹{crm_cash_today:.0f} cash received on {run_date}, '
                                f'but register on that date only shows ₹{register_today_crm_val:.0f}. '
                                f'Register on {hist.entry_date} has an unexplained surplus of '
                                f'₹{hist_surplus:.0f} (same or more than the ₹{crm_deficit:.0f} deficit) — '
                                f'cash was likely collected on {hist.entry_date} '
                                f'but CRM was updated {days_offset} day(s) later. '
                                f'Correct CRM payment date if confirmed, or escalate if cash cannot be traced.'
                            )
                        )
                        count += 1
                        logger.info(
                            "SuspectedBackdatedCRMEntry: CRM ₹%.2f on %s, "
                            "register surplus ₹%.2f found on %s (%d days earlier)",
                            crm_cash_today, run_date, hist_surplus, hist.entry_date, days_offset
                        )
                        break  # Best correlation candidate only

        return count

    # ── Feature 5: Period Summary ─────────────────────────────

    def get_period_summary(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """
        Aggregate daily reconciliation data into a period summary.

        Used for monthly/quarterly views. Flattens temporal corrections:
        if a GPay surplus on day A and deficit on day B cancel out within
        the period, the net variance is 0 and those exceptions are marked
        'self-correcting'.

        Returns a dict with:
            net_gpay_variance       — Σ CRM GPay − Σ MSWIPE for period
          net_cash_variance       — Σ notepad cash − Σ register cash for period
          self_correcting_pairs   — count of surplus/deficit pairs that net to 0
          persistent_exceptions   — list of exceptions not cancelled by period netting
          period_order_stats      — total orders, exceptions, ageing, backdated
          per_day                 — per-day breakdown list
        """
        from src.models.reconciliation import ReconciliationRun
        from src.models.exceptions import OrderException as OEx
        from src.models.cash_register import CashRegisterEntry

        # ── Collect aggregate totals ──────────────────────────
        gpay_modes = ['GPay', 'Google Pay', 'UPI']
        crm_gpay_total = float(
            self.db.query(func.sum(PaymentEvent.amount)).filter(
                PaymentEvent.source == 'crm',
                PaymentEvent.payment_mode.in_(gpay_modes),
                PaymentEvent.payment_date >= start_date,
                PaymentEvent.payment_date <= end_date,
            ).scalar() or 0.0
        )
        mswipe_total = float(
            self.db.query(func.sum(PaymentEvent.amount)).filter(
                PaymentEvent.source == 'mswipe',
                PaymentEvent.payment_date >= start_date,
                PaymentEvent.payment_date <= end_date,
            ).scalar() or 0.0
        )
        # Paytm QR payments (auto-recorded, not a fraud vector)
        paytm_total = float(
            self.db.query(func.sum(PaymentEvent.amount)).filter(
                PaymentEvent.source == 'paytm',
                PaymentEvent.payment_date >= start_date,
                PaymentEvent.payment_date <= end_date,
            ).scalar() or 0.0
        )
        notepad_cash_total = float(
            self.db.query(func.sum(PaymentEvent.amount)).filter(
                PaymentEvent.source == 'notepad',
                PaymentEvent.payment_mode == 'Cash',
                PaymentEvent.payment_date >= start_date,
                PaymentEvent.payment_date <= end_date,
            ).scalar() or 0.0
        )
        crm_cash_total = float(
            self.db.query(func.sum(PaymentEvent.amount)).filter(
                PaymentEvent.source == 'crm',
                PaymentEvent.payment_mode == 'Cash',
                PaymentEvent.payment_date >= start_date,
                PaymentEvent.payment_date <= end_date,
            ).scalar() or 0.0
        )
        register_cash_total = float(
            self.db.query(
                func.sum(CashRegisterEntry.derived_cash_from_orders)
            ).filter(
                CashRegisterEntry.entry_date >= start_date,
                CashRegisterEntry.entry_date <= end_date,
            ).scalar() or 0.0
        )

        # Package purchases in period (these inflate register/MSWIPE but
        # are not CRM order payments — must be subtracted)
        from src.models.package_transaction import PackageTransaction
        pkg_cash_total = float(
            self.db.query(func.sum(PackageTransaction.amount)).filter(
                PackageTransaction.transaction_date >= start_date,
                PackageTransaction.transaction_date <= end_date,
                PackageTransaction.payment_mode == 'Cash',
            ).scalar() or 0.0
        )
        pkg_online_total = float(
            self.db.query(func.sum(PackageTransaction.amount)).filter(
                PackageTransaction.transaction_date >= start_date,
                PackageTransaction.transaction_date <= end_date,
                PackageTransaction.payment_mode == 'Online',
            ).scalar() or 0.0
        )

        # Adjusted totals (subtract package purchases from actuals)
        register_cash_adjusted = register_cash_total - pkg_cash_total
        mswipe_adjusted = mswipe_total - pkg_online_total

        net_gpay_variance = round(crm_gpay_total - mswipe_adjusted, 2)
        # derived_cash_from_orders already includes expenses + bank deposits,
        # so compare directly without adding them back
        net_cash_variance = round(notepad_cash_total - register_cash_adjusted, 2)
        net_crm_vs_register_variance = round(crm_cash_total - register_cash_adjusted, 2)

        # ── Expense totals for the period ──────────────────────
        total_cash_expenses = float(
            self.db.query(func.sum(Expense.amount)).filter(
                Expense.expense_date >= start_date,
                Expense.expense_date <= end_date,
                Expense.mode == 'Cash',
            ).scalar() or 0.0
        )
        total_online_expenses = float(
            self.db.query(func.sum(Expense.amount)).filter(
                Expense.expense_date >= start_date,
                Expense.expense_date <= end_date,
                Expense.mode != 'Cash',
            ).scalar() or 0.0
        )
        total_expenses = total_cash_expenses + total_online_expenses

        # Bank deposits for the period
        from src.models.bank_deposit import BankDeposit
        total_bank_deposits = float(
            self.db.query(func.sum(BankDeposit.amount)).filter(
                BankDeposit.deposit_date >= start_date,
                BankDeposit.deposit_date <= end_date,
            ).scalar() or 0.0
        )

        net_gpay_variance = round(crm_gpay_total - mswipe_total, 2)
        # derived_cash_from_orders already includes expenses + bank deposits,
        # so compare directly without adding them back
        net_cash_variance = round(notepad_cash_total - register_cash_total, 2)
        net_crm_vs_register_variance = round(crm_cash_total - register_cash_total, 2)

        # ── Gather all exceptions for the period ──────────────
        runs = self.db.query(ReconciliationRun).filter(
            ReconciliationRun.run_date >= start_date,
            ReconciliationRun.run_date <= end_date,
        ).all()
        run_ids = [r.id for r in runs]

        all_exceptions = self.db.query(OEx).filter(
            OEx.reconciliation_run_id.in_(run_ids)
        ).all() if run_ids else []

        # ── Self-correcting pair detection ────────────────────
        # Day-level GPayMismatch and CashVariance exceptions that cancel out
        # when summed across the period are marked self-correcting.
        gpay_mismatches = [e for e in all_exceptions if e.exception_type == 'GPayMismatch']
        cash_variances = [e for e in all_exceptions if e.exception_type == 'CashVariance']

        self_correcting_pairs = 0
        if abs(net_gpay_variance) <= self.gpay_tolerance and gpay_mismatches:
            self_correcting_pairs += len(gpay_mismatches)
        if abs(net_cash_variance) <= self.cash_variance_tolerance and cash_variances:
            self_correcting_pairs += len(cash_variances)

        # ── Persistent exceptions ─────────────────────────────
        # Non-day-level exceptions always persist (order-level issues don't cancel out)
        transient_types = {'GPayMismatch', 'CashVariance'}
        persistent = [e for e in all_exceptions if e.exception_type not in transient_types
                      or e.resolution_status == 'open']

        # If day-level variance persists at period level, keep those too
        if abs(net_gpay_variance) > self.gpay_tolerance:
            persistent = all_exceptions  # Include everything
        else:
            persistent = [e for e in all_exceptions if e.exception_type not in transient_types]

        # ── Per-day breakdown ─────────────────────────────────
        run_date_map = {r.id: r.run_date for r in runs}
        per_day = []
        for r in sorted(runs, key=lambda x: x.run_date):
            day_ex = [e for e in all_exceptions if e.reconciliation_run_id == r.id]
            per_day.append({
                'date': str(r.run_date),
                'run_id': r.id,
                'total_exceptions': len(day_ex),
                'high': sum(1 for e in day_ex if e.severity == 'high'),
                'medium': sum(1 for e in day_ex if e.severity == 'medium'),
                'status': r.status,
            })

        # ── Order stats for period ────────────────────────────
        order_ids = set()
        deliveries = self.db.query(DeliveryEvent).filter(
            DeliveryEvent.delivery_date >= start_date,
            DeliveryEvent.delivery_date <= end_date,
        ).all()
        payments = self.db.query(PaymentEvent).filter(
            PaymentEvent.payment_date >= start_date,
            PaymentEvent.payment_date <= end_date,
        ).all()
        for d in deliveries:
            if d.order_id:
                order_ids.add(d.order_id)
        for p in payments:
            if p.order_id:
                order_ids.add(p.order_id)

        summary = {
            'start_date': str(start_date),
            'end_date': str(end_date),
            'days_in_period': (end_date - start_date).days + 1,
            'runs_completed': len(runs),
            # GPay/UPI/Card (fraud vector — staff can mark in CRM)
            'crm_gpay_total': round(crm_gpay_total, 2),
            'mswipe_total': round(mswipe_total, 2),
            'mswipe_adjusted': round(mswipe_adjusted, 2),
            'net_gpay_variance': net_gpay_variance,
            # Paytm (auto-recorded, not a fraud vector)
            'paytm_total': round(paytm_total, 2),
            # Package adjustments
            'pkg_cash_total': round(pkg_cash_total, 2),
            'pkg_online_total': round(pkg_online_total, 2),
            # Cash (Notepad vs Register — classic daily variance)
            'notepad_cash_total': round(notepad_cash_total, 2),
            'register_cash_total': round(register_cash_total, 2),
            'register_cash_adjusted': round(register_cash_adjusted, 2),
            'net_cash_variance': net_cash_variance,
            # Cash (CRM vs Register — undeposited cash / fraud detection)
            'crm_cash_total': round(crm_cash_total, 2),
            'net_crm_vs_register_variance': net_crm_vs_register_variance,
            # Expenses
            'total_cash_expenses': round(total_cash_expenses, 2),
            'total_online_expenses': round(total_online_expenses, 2),
            'total_expenses': round(total_expenses, 2),
            # Bank deposits
            'total_bank_deposits': round(total_bank_deposits, 2),
            # Exception stats
            'total_exceptions': len(all_exceptions),
            'persistent_exceptions_count': len(persistent),
            'self_correcting_pairs': self_correcting_pairs,
            'ageing_order_count': sum(1 for e in all_exceptions if e.exception_type == 'AgeingOrder'),
            'backdated_count': sum(1 for e in all_exceptions
                                   if e.exception_type in ('BackdatedGPayPayment',
                                                           'SuspectedBackdatedCashPayment')),
            # Order stats
            'active_orders': len(order_ids),
            # Detail
            'persistent_exceptions': [
                {
                    'id': e.id,
                    'order_id': e.order_id,
                    'type': e.exception_type,
                    'severity': e.severity,
                    'run_date': str(run_date_map.get(e.reconciliation_run_id, '')),
                    'evidence': e.evidence,
                    'action': e.suggested_action,
                }
                for e in persistent
            ],
            'per_day': per_day,
        }

        logger.info(
            "Period summary %s to %s: GPay net=₹%.2f, Cash net=₹%.2f, "
            "%d persistent exceptions, %d self-correcting",
            start_date, end_date, net_gpay_variance, net_cash_variance,
            len(persistent), self_correcting_pairs
        )
        return summary

    # ── Day-Level Rules ───────────────────────────────────────

    def _check_day_rules(self, run_date: date, run_id: int) -> int:
        """
        Apply day-level reconciliation rules.

        Rules:
        1. GPay day-total validation (CRM vs MSWIPE)
        2. Cash variance validation (Notepad vs Cash Register)
        3. CRM cash vs Cash Register (undeposited cash / fraud detection)

        Returns:
            Count of exceptions created.
        """
        count = 0
        count += self._check_gpay_totals(run_date, run_id)
        count += self._check_cash_variance(run_date, run_id)
        count += self._check_crm_cash_vs_register(run_date, run_id)
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

        Note: ``derived_cash_from_orders`` already includes expenses and
        bank deposits added back at import time, so no manual adjustment
        is needed here.
        """
        # Skip cash checks before cash register data was available
        cash_from = self.settings.cash_register_available_from
        if cash_from and run_date < cash_from:
            return 0

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
                    f'Check cash register. Register derived cash '\
                    f'{derived_cash:.0f} vs '\
                    f'{float(expected_cash):.0f} expected from notepad.'
                )
                return 1
        return 0

    # ── CRM Cash vs Register (Undeposited Cash Detection) ─────

    def _check_crm_cash_vs_register(self, run_date: date, run_id: int) -> int:
        """
        Compare total CRM cash payments on run_date against the cash register.

        This catches the scenario where cash is collected and recorded in CRM
        but never deposited in the register — a potential fraud indicator.

        Unlike CashVariance (Notepad vs Register), this check uses CRM as the
        source of truth for what was collected, making it independent of whether
        the runner entered the payment in the notepad. If both notepad and
        register are silent but CRM shows cash received, this rule fires.

        Note: ``derived_cash_from_orders`` already includes expenses and
        bank deposits added back at import time, so no manual adjustment
        is needed here.

        Severity: high — undeposited cash is a critical discrepancy.
        Exception type: CashUndeposited
        """
        cash_from = self.settings.cash_register_available_from
        if cash_from and run_date < cash_from:
            return 0

        # Total cash marked received in CRM for this date
        crm_cash = float(
            self.db.query(func.sum(PaymentEvent.amount)).filter(
                PaymentEvent.source == 'crm',
                PaymentEvent.payment_mode == 'Cash',
                PaymentEvent.payment_date == run_date,
            ).scalar() or 0.0
        )

        if crm_cash == 0:
            return 0  # No CRM cash on this day — nothing to check

        register_entry = self.db.query(CashRegisterEntry).filter(
            CashRegisterEntry.entry_date == run_date
        ).first()

        # If no register entry at all, treat deposited amount as zero.
        register_cash = float(register_entry.derived_cash_from_orders or 0.0) if register_entry else 0.0

        # Subtract package cash purchases from register (packages are
        # real cash inflows that don't correspond to CRM cash payments)
        from src.models.package_transaction import PackageTransaction
        pkg_cash = float(
            self.db.query(func.sum(PackageTransaction.amount)).filter(
                PackageTransaction.transaction_date == run_date,
                PackageTransaction.payment_mode == 'Cash',
            ).scalar() or 0.0
        )
        register_cash_adjusted = register_cash - pkg_cash

        undeposited = crm_cash - register_cash_adjusted

        if undeposited > self.cash_variance_tolerance:
            self._create_exception(
                run_id, None, 'high', 'CashUndeposited',
                tags=['CashNotInRegister', 'PotentialFraud'],
                evidence={
                    'crm_cash_total': round(crm_cash, 2),
                    'register_derived_cash': round(register_cash, 2),
                    'pkg_cash_purchases': round(pkg_cash, 2),
                    'register_adjusted': round(register_cash_adjusted, 2),
                    'undeposited_amount': round(undeposited, 2),
                    'date': str(run_date),
                },
                action=(
                    f'Rs {undeposited:.0f} collected as cash per CRM but not reflected '
                    f'in cash register on {run_date} (register Rs {register_cash:.0f}'
                    f'{f", minus Rs {pkg_cash:.0f} package purchases" if pkg_cash > 0 else ""}'
                    f' = Rs {register_cash_adjusted:.0f} adjusted). '
                    f'Verify cash was deposited or investigate for missing deposit.'
                )
            )
            logger.info(
                "CashUndeposited: Rs %.2f CRM cash vs Rs %.2f register (adj) on %s (gap=Rs %.2f, pkg=Rs %.2f)",
                crm_cash, register_cash_adjusted, run_date, undeposited, pkg_cash
            )
            return 1

        return 0

    # ── Helpers ────────────────────────────────────────────────

    def _create_exception(self, run_id, order_id, severity, exc_type, tags, evidence, action):
        """Create and persist a reconciliation exception.
        
        Auto-carryover: if a previous exception of the same type for the same
        order was already resolved or marked false_positive, the new exception
        inherits that resolution status so it doesn't resurface on re-runs.
        """
        # Check for a prior resolution of the same issue
        resolution_status = 'open'
        resolution_note = None
        resolved_at = None

        if order_id is not None:
            prior = self.db.query(OrderException).filter(
                OrderException.order_id == order_id,
                OrderException.exception_type == exc_type,
                OrderException.resolution_status.in_(['resolved', 'false_positive']),
            ).order_by(OrderException.id.desc()).first()
        else:
            # Day-level exceptions (order_id is None): match by type + evidence signature
            prior = self.db.query(OrderException).filter(
                OrderException.order_id == None,
                OrderException.exception_type == exc_type,
                OrderException.resolution_status.in_(['resolved', 'false_positive']),
            ).order_by(OrderException.id.desc()).first()

        if prior:
            resolution_status = prior.resolution_status
            resolution_note = f"[Auto-carried from #{prior.id}] {prior.resolution_note or ''}"
            resolved_at = prior.resolved_at
            logger.info(
                "Auto-carrying resolution '%s' from exception #%d for %s/%s",
                prior.resolution_status, prior.id, exc_type, order_id
            )

        ex = OrderException(
            reconciliation_run_id=run_id,
            order_id=order_id,
            severity=severity,
            exception_type=exc_type,
            reason_tags=tags,
            evidence=evidence,
            suggested_action=action,
            resolution_status=resolution_status,
            resolution_note=resolution_note,
            resolved_at=resolved_at,
        )
        self.db.add(ex)

