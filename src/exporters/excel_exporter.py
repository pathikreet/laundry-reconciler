import pandas as pd
from sqlalchemy.orm import Session
from src.models.reconciliation import ReconciliationRun
from src.models.orders import Order
from src.models.exceptions import OrderException
from src.models.deliveries import DeliveryEvent
from src.models.payments import PaymentEvent
from src.models.cash_register import CashRegisterEntry

class ExcelExporter:
    def __init__(self, db_session: Session):
        self.db = db_session

    def export_run(self, run_id: int, output_path: str):
        run = self.db.get(ReconciliationRun, run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            # 1. Exceptions Sheet
            exceptions_data = []
            for ex in run.exceptions:
                order_num = ""
                if ex.order:
                    order_num = ex.order.order_number

                exceptions_data.append({
                    'Order Number': order_num,
                    'Severity': ex.severity,
                    'Type': ex.exception_type,
                    'Reason': ", ".join(ex.reason_tags) if ex.reason_tags else "",
                    'Evidence': str(ex.evidence),
                    'Action': ex.suggested_action,
                    'Status': ex.resolution_status
                })

            if exceptions_data:
                pd.DataFrame(exceptions_data).to_excel(writer, sheet_name='Exceptions', index=False)
            else:
                pd.DataFrame({'Message': ['No exceptions found']}).to_excel(writer, sheet_name='Exceptions', index=False)

            # 2. Daily Summary
            # We can calculate some basic stats here if summary_stats is empty
            summary_data = []
            if run.summary_stats:
                summary_data.append(run.summary_stats)
            else:
                # Basic stats
                summary_data.append({'Run Date': run.run_date, 'Status': run.status})

            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Daily_Summary', index=False)

            # 3. Unmatched Notepad (Global? Or just for this date?)
            # Usually users want to see ALL unmatched to fix them.
            unmatched_notepad = self.db.query(DeliveryEvent).filter(
                DeliveryEvent.source == 'notepad',
                DeliveryEvent.order_id == None
            ).all()
            unmatched_np_data = []
            for d in unmatched_notepad:
                unmatched_np_data.append({
                    'Date': d.delivery_date,
                    'Customer': d.customer_name,
                    'Amount': d.amount_collected,
                    'Mode': d.payment_mode,
                    'Runner': d.runner_name
                })

            if unmatched_np_data:
                pd.DataFrame(unmatched_np_data).to_excel(writer, sheet_name='Unmatched_Notepad', index=False)
            else:
                 pd.DataFrame({'Message': ['No unmatched notepad entries']}).to_excel(writer, sheet_name='Unmatched_Notepad', index=False)

            # 4. Unmatched MSWIPE
            unmatched_mswipe = self.db.query(PaymentEvent).filter(
                PaymentEvent.source == 'mswipe',
                PaymentEvent.order_id == None
            ).all()
            unmatched_ms_data = []
            for p in unmatched_mswipe:
                unmatched_ms_data.append({
                    'Date': p.payment_date,
                    'Amount': p.amount,
                    'Ref': str(p.mswipe_ref_ids) if p.mswipe_ref_ids else "",
                    'Original Mode': p.original_mode
                })

            if unmatched_ms_data:
                pd.DataFrame(unmatched_ms_data).to_excel(writer, sheet_name='Unmatched_MSWIPE', index=False)
            else:
                pd.DataFrame({'Message': ['No unmatched MSWIPE entries']}).to_excel(writer, sheet_name='Unmatched_MSWIPE', index=False)
