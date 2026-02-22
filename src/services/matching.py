from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import List, Optional, Tuple, Dict, Any
from rapidfuzz import process, fuzz
from datetime import timedelta, date
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent

class MatchingService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.amount_tolerance = 2.0
        self.fuzzy_name_score = 82.0
        self.date_proximity = 3 # days

    def match_notepad_deliveries(self):
        """
        Matches unlinked Notepad delivery events to orders.
        """
        deliveries = self.db.query(DeliveryEvent).filter(
            DeliveryEvent.order_id == None,
            DeliveryEvent.source == 'notepad'
        ).all()

        for delivery in deliveries:
            # 1. Exact match by Order Number
            raw_order_no = None
            if delivery.raw_data:
                raw_order_no = delivery.raw_data.get('Order Number') or delivery.raw_data.get('order_number')

            matched_order = None
            evidence = {}
            score = 0.0

            if raw_order_no:
                matched_order = self.db.query(Order).filter(
                    Order.order_number == str(raw_order_no)
                ).first()
                if matched_order:
                    score = 1.0
                    evidence = {'method': 'exact_order_number', 'value': raw_order_no}

            # 2. Fuzzy Match
            if not matched_order and delivery.customer_name and delivery.amount_collected is not None:
                matched_order, score, evidence = self._find_fuzzy_order(
                    name=delivery.customer_name,
                    amount=float(delivery.amount_collected or 0),
                    event_date=delivery.delivery_date
                )

            if matched_order and score >= (self.fuzzy_name_score / 100.0):
                delivery.order_id = matched_order.id
                delivery.confidence_score = score
                delivery.match_evidence = evidence

        self.db.commit()

    def match_mswipe_payments(self):
        """
        Matches unlinked MSWIPE payments to Orders.
        """
        payments = self.db.query(PaymentEvent).filter(
            PaymentEvent.order_id == None,
            PaymentEvent.source == 'mswipe'
        ).all()

        for payment in payments:
            # Strategy: Find orders with CRM payments (GPay) of similar amount around the date
            # OR orders with notepad deliveries of similar amount?
            # Primary link is usually to CRM Order to verify it.

            # Find CRM PaymentEvents (GPay/UPI) with similar amount and date
            start_date = payment.payment_date - timedelta(days=self.date_proximity)
            end_date = payment.payment_date + timedelta(days=self.date_proximity)

            crm_payments = self.db.query(PaymentEvent).join(Order).filter(
                PaymentEvent.source == 'crm',
                # PaymentEvent.payment_mode.in_(['GPay', 'UPI', 'Paytm', 'PhonePe']), # This should be normalized
                # Assuming normalized to 'GPay'
                or_(PaymentEvent.payment_mode == 'GPay', PaymentEvent.payment_mode == 'UPI'),
                PaymentEvent.amount >= float(payment.amount) - self.amount_tolerance,
                PaymentEvent.amount <= float(payment.amount) + self.amount_tolerance,
                PaymentEvent.payment_date >= start_date,
                PaymentEvent.payment_date <= end_date
            ).all()

            # If multiple CRM payments match, we have ambiguity.
            # But if we find one that is NOT yet linked to an MSWIPE payment?
            # Wait, `PaymentEvent` (CRM) doesn't have a link to `PaymentEvent` (MSWIPE).
            # We are linking MSWIPE -> Order.
            # If multiple CRM payments for SAME Order match? Then it's the same Order.
            # If multiple CRM payments for DIFFERENT Orders match? Ambiguity.

            candidate_orders = {}
            for cp in crm_payments:
                if cp.order_id:
                     candidate_orders[cp.order_id] = cp

            if len(candidate_orders) == 1:
                order_id = list(candidate_orders.keys())[0]
                payment.order_id = order_id
                payment.confidence_score = 0.9
                payment.match_evidence = {'method': 'crm_gpay_match', 'crm_payment_id': candidate_orders[order_id].id}

            # TODO: handle ambiguity or use other signals

        self.db.commit()

    def _find_fuzzy_order(self, name: str, amount: float, event_date: date) -> Tuple[Optional[Order], float, Dict[str, Any]]:
        # 1. Filter by date window (Order Date)
        start_date = event_date - timedelta(days=10) # Order could be placed much earlier
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

            # Score Amount (Binary or gradient?)
            # If amount matches within tolerance, boost score?
            amount_score = 0.0
            diff = abs(float(order.order_amount) - amount)
            if diff <= self.amount_tolerance:
                amount_score = 1.0
            elif diff <= 10: # small variance
                amount_score = 0.5

            # Combined Score
            # Weight name higher?
            # If amount matches perfectly, we are very confident.
            # If amount mismatches significantly, maybe it's partial payment?
            # But here we are matching DELIVERY amount collected.
            # Often collected = order amount.

            final_score = (name_score * 0.6) + (amount_score * 0.4)

            if final_score > best_score:
                best_score = final_score
                best_match = order
                best_evidence = {
                    'method': 'fuzzy',
                    'name_score': name_score,
                    'amount_score': amount_score,
                    'name_matched': order.customer_name,
                    'amount_matched': float(order.order_amount)
                }

        return best_match, best_score, best_evidence
