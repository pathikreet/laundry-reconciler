import logging
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.models.reconciliation import ReconciliationRun
from src.models.orders import Order
from src.models.exceptions import OrderException
from src.models.deliveries import DeliveryEvent
from src.models.payments import PaymentEvent
from src.models.cash_register import CashRegisterEntry
from src.models.audit import AuditLog
from src.exceptions import ExportError

logger = logging.getLogger(__name__)


class ExcelExporter:
    """
    Exports reconciliation results to a multi-sheet Excel workbook.

    Sheets (per PRD §4.2):
    1. Reconciled_Orders  2. Exceptions  3. Unmatched_Notepad
    4. Unmatched_MSWIPE   5. Daily_Summary  6. Audit_Log
    """
    def __init__(self, db_session: Session):
        self.db = db_session

    def export_run(self, run_id: int, output_path: str):
        run = self.db.get(ReconciliationRun, run_id)
        if not run:
            raise ExportError(f"Run {run_id} not found", details={"run_id": run_id})

        try:
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                self._write_reconciled_orders(writer, run)
                self._write_exceptions(writer, run)
                self._write_unmatched_notepad(writer)
                self._write_unmatched_mswipe(writer)
                self._write_daily_summary(writer, run)
                self._write_audit_log(writer, run)
            logger.info("Report exported to %s for run %d", output_path, run_id)
        except ExportError:
            raise
        except Exception as e:
            raise ExportError(f"Export failed: {e}", details={"run_id": run_id, "error": str(e)})

    def _write_reconciled_orders(self, writer, run):
        order_ids = set()
        for d in self.db.query(DeliveryEvent).filter(DeliveryEvent.delivery_date == run.run_date).all():
            if d.order_id: order_ids.add(d.order_id)
        for p in self.db.query(PaymentEvent).filter(PaymentEvent.payment_date == run.run_date).all():
            if p.order_id: order_ids.add(p.order_id)

        orders = self.db.query(Order).filter(Order.id.in_(order_ids)).all() if order_ids else []
        data = []
        for o in orders:
            paid = sum(float(p.amount) for p in o.payments)
            excs = self.db.query(OrderException).filter_by(reconciliation_run_id=run.id, order_id=o.id).all()
            data.append({
                'Order Number': o.order_number, 'Customer': o.customer_name,
                'Amount': float(o.order_amount), 'Paid': round(paid, 2),
                'Balance': round(float(o.order_amount) - paid, 2),
                'Status': 'Exception' if excs else 'Clean',
                'Exceptions': ', '.join(e.exception_type for e in excs)
            })
        self._write_sheet(writer, 'Reconciled_Orders', data, 'No orders found')

    def _write_exceptions(self, writer, run):
        data = []
        for ex in run.exceptions:
            data.append({
                'Order Number': ex.order.order_number if ex.order else 'Day-Level',
                'Severity': ex.severity, 'Type': ex.exception_type,
                'Reason': ", ".join(ex.reason_tags) if ex.reason_tags else "",
                'Evidence': str(ex.evidence),
                'Action': ex.suggested_action, 'Status': ex.resolution_status
            })
        self._write_sheet(writer, 'Exceptions', data, 'No exceptions found')

    def _write_unmatched_notepad(self, writer):
        items = self.db.query(DeliveryEvent).filter(
            DeliveryEvent.source == 'notepad', DeliveryEvent.order_id == None).all()
        data = [{'Date': d.delivery_date, 'Customer': d.customer_name,
                 'Amount': float(d.amount_collected or 0), 'Mode': d.payment_mode,
                 'Runner': d.runner_name} for d in items]
        self._write_sheet(writer, 'Unmatched_Notepad', data, 'No unmatched notepad entries')

    def _write_unmatched_mswipe(self, writer):
        items = self.db.query(PaymentEvent).filter(
            PaymentEvent.source == 'mswipe', PaymentEvent.order_id == None).all()
        data = [{'Date': p.payment_date, 'Amount': float(p.amount),
                 'Ref': str(p.mswipe_ref_ids) if p.mswipe_ref_ids else "",
                 'Original Mode': p.original_mode} for p in items]
        self._write_sheet(writer, 'Unmatched_MSWIPE', data, 'No unmatched MSWIPE entries')

    def _write_daily_summary(self, writer, run):
        total_ex = self.db.query(func.count(OrderException.id)).filter_by(
            reconciliation_run_id=run.id).scalar() or 0
        high = self.db.query(func.count(OrderException.id)).filter_by(
            reconciliation_run_id=run.id, severity='high').scalar() or 0
        crm_gpay = float(self.db.query(func.sum(PaymentEvent.amount)).filter(
            PaymentEvent.source == 'crm', PaymentEvent.payment_mode.in_(['GPay', 'Google Pay', 'UPI']),
            PaymentEvent.payment_date == run.run_date).scalar() or 0)
        mswipe = float(self.db.query(func.sum(PaymentEvent.amount)).filter(
            PaymentEvent.source == 'mswipe',
            PaymentEvent.payment_date == run.run_date).scalar() or 0)

        data = [{'Run Date': run.run_date, 'Status': run.status,
                 'Total Exceptions': total_ex, 'High Severity': high,
                 'CRM GPay': round(crm_gpay, 2), 'MSWIPE Total': round(mswipe, 2),
                 'GPay Variance': round(crm_gpay - mswipe, 2)}]
        pd.DataFrame(data).to_excel(writer, sheet_name='Daily_Summary', index=False)

    def _write_audit_log(self, writer, run):
        entries = self.db.query(AuditLog).filter(
            AuditLog.reconciliation_run_id == run.id
        ).order_by(AuditLog.performed_at.desc()).all()
        data = [{'Timestamp': a.performed_at, 'Action': a.action_type,
                 'Entity': a.entity_type, 'Entity ID': a.entity_id,
                 'By': a.performed_by} for a in entries]
        self._write_sheet(writer, 'Audit_Log', data, 'No audit entries')

    @staticmethod
    def _write_sheet(writer, name, data, empty_msg):
        if data:
            pd.DataFrame(data).to_excel(writer, sheet_name=name, index=False)
        else:
            pd.DataFrame({'Message': [empty_msg]}).to_excel(writer, sheet_name=name, index=False)
