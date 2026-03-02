import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import List, Optional, Tuple, Dict, Any
from rapidfuzz import process, fuzz
from datetime import timedelta, date
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent
from src.config.settings import Settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 100  # Process unmatched records in batches to limit memory usage


class MatchingService:
    def __init__(self, db_session: Session, settings: Settings = None):
        self.db = db_session
        self.settings = settings or Settings()
        self.amount_tolerance = self.settings.amount_tolerance
        self.fuzzy_name_score = self.settings.fuzzy_name_threshold * 100
        self.date_proximity = self.settings.date_window_days

    def match_notepad_deliveries(self) -> Dict[str, Any]:
        """
        Matches unlinked Notepad delivery events to orders.

        Uses a two-pass strategy:
        1. Exact match by order number (confidence = 1.0)
        2. Fuzzy match by customer name + amount + date (confidence = weighted score)

        Returns:
            Summary dict with match statistics.
        """
        stats = {"exact": 0, "fuzzy": 0, "unmatched": 0, "total": 0}

        # Process in batches to limit memory usage
        offset = 0
        while True:
            deliveries = self.db.query(DeliveryEvent).filter(
                DeliveryEvent.order_id == None,
                DeliveryEvent.source == 'notepad'
            ).limit(BATCH_SIZE).offset(offset).all()

            if not deliveries:
                break

            for delivery in deliveries:
                stats["total"] += 1

                # 1. Exact match by Order Number
                raw_order_no = None
                if delivery.raw_data:
                    raw_order_no = delivery.raw_data.get('Order Number') or delivery.raw_data.get('order_number')

                matched_order = None
                evidence = {}
                score = 0.0

                if raw_order_no:
                    matched_order = self.db.query(Order).filter(
                        Order.order_number == str(raw_order_no).strip()
                    ).first()
                    if matched_order:
                        score = 1.0
                        evidence = {
                            'method': 'exact_order_number',
                            'value': raw_order_no,
                            'explanation': f"Exact match on order number '{raw_order_no}'"
                        }
                        stats["exact"] += 1

                # 2. Fuzzy Match
                if not matched_order and delivery.customer_name and delivery.amount_collected is not None:
                    matched_order, score, evidence = self._find_fuzzy_order(
                        name=delivery.customer_name,
                        amount=float(delivery.amount_collected or 0),
                        event_date=delivery.delivery_date
                    )
                    if matched_order:
                        stats["fuzzy"] += 1

                if matched_order and score >= (self.fuzzy_name_score / 100.0):
                    delivery.order_id = matched_order.id
                    delivery.confidence_score = score
                    delivery.match_evidence = evidence
                else:
                    stats["unmatched"] += 1

            offset += BATCH_SIZE

        self.db.commit()
        logger.info("Notepad matching: %s", stats)
        return stats

    def match_mswipe_payments(self) -> Dict[str, Any]:
        """
        Matches unlinked MSWIPE payments to Orders via CRM GPay payments.

        Strategy: Find CRM payment events (GPay/UPI) with similar amount and date,
        then link the MSWIPE payment to the same order.

        Returns:
            Summary dict with match statistics.
        """
        stats = {"matched": 0, "ambiguous": 0, "unmatched": 0, "total": 0}

        offset = 0
        while True:
            payments = self.db.query(PaymentEvent).filter(
                PaymentEvent.order_id == None,
                PaymentEvent.source == 'mswipe'
            ).limit(BATCH_SIZE).offset(offset).all()

            if not payments:
                break

            for payment in payments:
                stats["total"] += 1

                start_date = payment.payment_date - timedelta(days=self.date_proximity)
                end_date = payment.payment_date + timedelta(days=self.date_proximity)

                crm_payments = self.db.query(PaymentEvent).join(Order).filter(
                    PaymentEvent.source == 'crm',
                    PaymentEvent.payment_mode.in_(['GPay', 'Google Pay', 'UPI']),
                    PaymentEvent.amount >= float(payment.amount) - self.amount_tolerance,
                    PaymentEvent.amount <= float(payment.amount) + self.amount_tolerance,
                    PaymentEvent.payment_date >= start_date,
                    PaymentEvent.payment_date <= end_date
                ).all()

                candidate_orders = {}
                for cp in crm_payments:
                    if cp.order_id:
                        candidate_orders[cp.order_id] = cp

                if len(candidate_orders) == 1:
                    order_id = list(candidate_orders.keys())[0]
                    crm_payment = candidate_orders[order_id]
                    payment.order_id = order_id
                    payment.confidence_score = 0.9
                    payment.match_evidence = {
                        'method': 'crm_gpay_match',
                        'crm_payment_id': crm_payment.id,
                        'explanation': (
                            f"Matched to order via CRM GPay payment (ID: {crm_payment.id}). "
                            f"Amount: ₹{float(payment.amount):.2f} ≈ ₹{float(crm_payment.amount):.2f}, "
                            f"Date: {payment.payment_date} within {self.date_proximity} days of {crm_payment.payment_date}."
                        )
                    }
                    stats["matched"] += 1
                elif len(candidate_orders) > 1:
                    # Ambiguous — multiple CRM payments match; flag for manual review
                    payment.match_evidence = {
                        'method': 'ambiguous',
                        'candidate_count': len(candidate_orders),
                        'explanation': (
                            f"Ambiguous: {len(candidate_orders)} CRM GPay payments match "
                            f"amount ₹{float(payment.amount):.2f} within date window. Manual review needed."
                        )
                    }
                    stats["ambiguous"] += 1
                else:
                    stats["unmatched"] += 1

            offset += BATCH_SIZE

        self.db.commit()
        logger.info("MSWIPE matching: %s", stats)
        return stats

    def _find_fuzzy_order(self, name: str, amount: float, event_date: date) -> Tuple[Optional[Order], float, Dict[str, Any]]:
        """
        Find the best fuzzy-matching order for a delivery event.

        Scoring:
        - Name similarity (60% weight): token_sort_ratio via rapidfuzz
        - Amount match (40% weight): binary within tolerance, gradient for small variances

        Returns:
            Tuple of (matched_order, confidence_score, evidence_dict)
        """
        # Filter by date window (Order Date could be much earlier than delivery)
        start_date = event_date - timedelta(days=10)
        end_date = event_date + timedelta(days=1)

        candidates = self.db.query(Order).filter(
            Order.order_date >= start_date,
            Order.order_date <= end_date
        ).all()

        best_match = None
        best_score = 0.0
        best_evidence = {}

        for order in candidates:
            # Score Name
            name_score = fuzz.token_sort_ratio(name, order.customer_name) / 100.0

            # Score Amount
            amount_score = 0.0
            diff = abs(float(order.order_amount) - amount)
            if diff <= self.amount_tolerance:
                amount_score = 1.0
            elif diff <= 10:
                amount_score = 0.5

            # Combined weighted score
            final_score = (name_score * 0.6) + (amount_score * 0.4)

            if final_score > best_score:
                best_score = final_score
                best_match = order
                best_evidence = {
                    'method': 'fuzzy',
                    'name_score': round(name_score, 3),
                    'amount_score': round(amount_score, 3),
                    'final_score': round(final_score, 3),
                    'name_matched': order.customer_name,
                    'amount_matched': float(order.order_amount),
                    'explanation': (
                        f"Fuzzy match: name '{name}' ≈ '{order.customer_name}' "
                        f"(similarity: {name_score:.0%}), "
                        f"amount ₹{amount:.2f} vs ₹{float(order.order_amount):.2f} "
                        f"(diff: ₹{diff:.2f}). "
                        f"Combined confidence: {final_score:.0%}."
                    )
                }

        return best_match, best_score, best_evidence
