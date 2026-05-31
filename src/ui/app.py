"""
Digital Accountant — Streamlit UI

Guided import wizard + reconciliation dashboard.
Import order: CRM Sales → CRM Orders → CRM Delivery → MSWIPE → Notepad → Cash Register
"""
import streamlit as st
import pandas as pd
import os
import sys
import io
import tempfile
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# Configure logging so service-layer logs appear in the terminal
# Streamlit overrides the root logger; this ensures our 'src.*' logs are visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
# Suppress noisy Streamlit/watchdog logs
logging.getLogger('streamlit').setLevel(logging.WARNING)
logging.getLogger('watchdog').setLevel(logging.WARNING)

from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.db.init_db import init_db
from src.importers.crm import CRMImporter
from src.importers.crm_delivery import CRMDeliveryImporter
from src.importers.crm_orders import CRMOrdersImporter
from src.importers.mswipe import MSwipeImporter
from src.importers.cash_register import CashRegisterImporter
from src.importers.notepad import NotepadImporter
from src.importers.expenses import ExpensesImporter
from src.services.matching import MatchingService
from src.services.reconciliation import ReconciliationService
from src.exporters.excel_exporter import ExcelExporter
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent
from src.models.expenses import Expense
from src.exceptions import LaundryReconcilerError

logger = logging.getLogger(__name__)

DB_PATH = "laundry_reconciler.db"
MAX_UPLOAD_MB = 50
ALLOWED_TYPES = ['csv', 'xlsx', 'xls']

# ── Exception Descriptions (shown as tooltips in the UI) ──
EXCEPTION_DESCRIPTIONS = {
    'DeliveredNotMarkedCRM': (
        '📦 Delivery recorded in Runner Notepad but no matching Delivery Event found in CRM. '
        'The order was physically delivered but CRM was not updated.'
    ),
    'DeliveredMissingNotepad': (
        '📋 CRM has a Delivery Event for this order, but the Runner Notepad has no entry. '
        'Either the runner forgot to note it, or the delivery did not happen as recorded.'
    ),
    'CreditPolicyViolation': (
        '💳 Order was delivered (per Notepad) but the outstanding balance exceeds the credit tolerance. '
        'Customer has not fully paid at the time of delivery.'
    ),
    'NotepadAmountMismatch': (
        '⚖️ The cash amount in the Runner Notepad differs from the CRM payment amount beyond tolerance. '
        'CRM is the authoritative source — the notepad entry may have an error.'
    ),
    'GPayMismatch': (
        '💳 Day-level: Total GPay recorded in CRM does not match the MSWIPE terminal total for the day. '
        'High severity if variance exceeds ₹100.'
    ),
    'CashVariance': (
        '💵 Day-level: Total cash collected per Runner Notepad does not match the Cash Register derived amount. '
        'Could indicate missing deposits or notepad errors.'
    ),
    'LatePayment': (
        '🕐 A CRM payment was recorded after the delivery date, beyond the allowed threshold days. '
        'Indicates payment was collected or entered late.'
    ),
    'CashUndeposited': (
        '🚨 Day-level: CRM shows cash received for the day, but the Cash Register (adjusted for '
        'package cash purchases) has no matching deposit. '
        'Independent of the Notepad — fires even if the runner skipped the notepad entry. '
        'Potential indicator of pocketing/fraud.'
    ),
    'NotepadPaymentNotInCRM': (
        '📝 Runner Notepad records a payment for an order, but CRM has no payment at all for that order. '
        'CRM is out of sync — staff may have forgotten to record the collection.'
    ),
    'GPayOrderMismatch': (
        '💳 CRM records a GPay payment for a specific order, but no MSWIPE transaction is linked to it. '
        'The GPay receipt may be on a different order number in MSWIPE, or missing entirely.'
    ),
    'CashOrderNoRegister': (
        '💵 CRM records a Cash payment for a specific order on a date where the Cash Register has no entry at all. '
        'Either the register was not imported for that date, or the cash was never deposited.'
    ),
    'PaymentNotConfirmedByNotepad': (
        '📋 CRM records an Online/Card payment (staff-entered), but the Runner Notepad has no corresponding entry. '
        'Low severity — the runner may have simply omitted the note.'
    ),
    'PaytmNotInQRData': (
        '📱 CRM auto-recorded a Paytm payment, but no matching transaction found in the Paytm QR data. '
        'Not a fraud risk — Paytm is auto-recorded. Likely a timing or data sync issue.'
    ),
    'PackageNotConfirmedByNotepad': (
        '📦 CRM auto-deducted a Package wallet payment, but the Runner Notepad has no delivery/payment entry '
        'for this order with Package mode. Not a fraud risk — runner may have omitted the note.'
    ),
    'AgeingOrder': (
        '⏰ Order was placed more than the configured ageing threshold days ago with no delivery recorded from any source. '
        'Outstanding balance still exists — needs follow-up.'
    ),
    'BackdatedGPayPayment': (
        '🕵️ CRM records a GPay payment on run_date, but no same-day MSWIPE match exists. '
        'A MSWIPE transaction of the same amount was found on an earlier date — payment was likely '
        'received earlier but CRM was entered late.'
    ),
    'SuspectedBackdatedCashPayment': (
        '🕵️ Cash deficit on run_date (Notepad > Register) correlates with a cash surplus on an earlier date '
        '(Register > Notepad). Payment likely collected earlier but recorded in the notepad late.'
    ),
    'SuspectedBackdatedCRMEntry': (
        '🕵️ CRM records cash received on run_date, but the Cash Register on that date is short. '
        'An earlier date\'s register has an unexplained surplus of a matching amount — '
        'cash was likely collected then, but CRM was only updated on run_date. '
        'Probable honest late entry (not pocketing) — verify and correct CRM date.'
    ),
}

def preview_uploaded_file(uploaded_file):
    """
    Displays a small preview of the uploaded file to reassure the user
    they uploaded the right data before importing.
    """
    try:
        uploaded_file.seek(0)
        file_ext = uploaded_file.name.split('.')[-1].lower()

        if file_ext in ['xlsx', 'xls']:
            xl = pd.ExcelFile(uploaded_file)
            st.caption(f"Sheets found: {', '.join(xl.sheet_names)}")
            df = xl.parse(xl.sheet_names[0], nrows=5)
        elif file_ext == 'csv':
            df = pd.read_csv(uploaded_file, nrows=5)
        else:
            st.warning("Preview not supported for this file type.")
            return

        st.dataframe(df, use_container_width=True)

    except Exception as e:
        st.warning(f"Could not generate preview: {e}")
    finally:
        # Crucial: Reset pointer so the actual import doesn't fail!
        uploaded_file.seek(0)

# Initialize DB if needed
if not os.path.exists(DB_PATH):
    init_db(DB_PATH)


# ── Helpers ───────────────────────────────────────────────

def get_session():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine)
    return Session()


def load_css():
    css_path = os.path.join(os.path.dirname(__file__), 'styles.css')
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


def validate_upload(uploaded_file):
    if uploaded_file is None:
        return False, "No file uploaded"
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        return False, f"File too large ({size_mb:.1f} MB). Max: {MAX_UPLOAD_MB} MB"
    ext = os.path.splitext(uploaded_file.name.lower())[1]
    if ext.lstrip('.') not in ALLOWED_TYPES:
        return False, f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_TYPES)}"
    return True, ""


def safe_import(importer, file_obj, suffix=None, **kwargs):
    # Determine the correct extension to preserve file format (e.g. .csv vs .xlsx)
    ext = os.path.splitext(file_obj.name)[1]
    if not ext:
        ext = suffix if suffix else ".xlsx"
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_obj.getbuffer())
        tmp_path = tmp.name
    try:
        result = importer.run(tmp_path, **kwargs)
        return True, result
    except LaundryReconcilerError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except PermissionError:
            pass  # Windows: file still locked by pandas/openpyxl, OS will clean up


def init_import_state():
    """Initialize session state for import tracking."""
    if 'imports' not in st.session_state:
        st.session_state.imports = {
            'crm_sales': {'done': False, 'result': None},
            'crm_orders': {'done': False, 'result': None},
            'crm_delivery': {'done': False, 'result': None},
            'mswipe': {'done': False, 'result': None},
            'notepad': {'done': False, 'result': None},
            'cash_register': {'done': False, 'result': None},
            'expenses': {'done': False, 'result': None},
            'paytm': {'done': False, 'result': None},
        }


def get_import_progress():
    """Return (completed, total) import step counts."""
    imports = st.session_state.get('imports', {})
    done = sum(1 for v in imports.values() if v.get('done'))
    return done, len(imports)

def navigate_to(page_name):
    """Helper callback to navigate without StreamlitAPIException."""
    st.session_state['nav_radio'] = page_name

# ── Step Card Renderer ────────────────────────────────────

def render_step_card(step_num, title, description, key, is_unlocked, session_db):
    """Render a single import step card with upload + preview + import."""
    state = st.session_state.imports[key]

    # Determine card status
    if state['done']:
        status_class = "complete"
        icon = "✅"
    elif is_unlocked:
        status_class = "active"
        icon = "📂"
    else:
        status_class = "locked"
        icon = "🔒"

    st.markdown(
        f'<div class="step-card {status_class}">'
        f'<strong>{icon} Step {step_num}: {title}</strong>'
        f'<br><span style="color:#666;font-size:0.85rem">{description}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    if state['done']:
        result = state['result']
        if result:
            cols = st.columns(3)
            cols[0].metric("Total Rows", result.get('total', '-'))
            cols[1].metric("Imported", result.get('imported', '-'))
            cols[2].metric("Errors", result.get('errors', 0))
        return

    if not is_unlocked:
        st.caption("⏳ Complete the previous required step first")
        return

    return True  # Signal to render the upload widget


def render_import_step(step_num, title, desc, key, importer_class, session_db,
                       is_unlocked, file_types=None, suffix=".xlsx", extra_kwargs=None):
    """Full import step: card + upload + preview + import button."""
    should_render = render_step_card(step_num, title, desc, key, is_unlocked, session_db)

    if should_render is not True:
        return

    file_types = file_types or ['csv', 'xlsx', 'xls']
    uploaded_files = st.file_uploader(f"Upload {title} (Multiple allowed)", type=file_types, key=f"upload_{key}", accept_multiple_files=True)

    if uploaded_files:
        for uf in uploaded_files:
            valid, msg = validate_upload(uf)
            if not valid:
                st.error(f"{uf.name}: {msg}")
                return

        # Data preview of first file
        first_file = uploaded_files[0]
        with st.expander(f"📋 Preview first 5 rows ({first_file.name})", expanded=False):
            try:
                if first_file.name.endswith('.csv'):
                    preview_df = pd.read_csv(first_file, nrows=5)
                else:
                    preview_df = pd.read_excel(first_file, nrows=5)
                st.dataframe(preview_df.astype(str), width='stretch')
                first_file.seek(0)  # Reset for import
            except Exception:
                st.warning("Could not preview file")

        if st.button(f"🚀 Import {len(uploaded_files)} File(s) for {title}", key=f"btn_{key}"):
            with st.spinner(f"Importing {len(uploaded_files)} file(s) for {title}..."):
                importer = importer_class(session_db)
                kwargs = extra_kwargs or {}
                
                total_res = {'total': 0, 'imported': 0, 'errors': 0}
                all_ok = True
                
                for uf in uploaded_files:
                    ok, result = safe_import(importer, uf, suffix=suffix, **kwargs)
                    if ok and isinstance(result, dict):
                        total_res['total'] += result.get('total', 0)
                        total_res['imported'] += result.get('imported', 0)
                        total_res['errors'] += result.get('errors', 0)
                    else:
                        st.error(f"❌ Import failed for {uf.name}: {result}")
                        all_ok = False
                        break

                if all_ok:
                    st.session_state.imports[key] = {'done': True, 'result': total_res}
                    st.success(f"✅ All {len(uploaded_files)} {title} file(s) imported successfully!")
                    if total_res['errors'] > 0:
                        st.warning(f"⚠️ {total_res['errors']} rows had issues and were skipped")
                    st.rerun()


# ── Notepad Manual Entry Form ─────────────────────────────

def _init_notepad_entries():
    """Initialize notepad entries in session state."""
    if 'notepad_entries' not in st.session_state:
        st.session_state.notepad_entries = []


def render_notepad_step(session_db, is_unlocked):
    """Step 5: Runner Notepad — file upload OR manual entry."""
    state = st.session_state.imports['notepad']

    if state['done']:
        icon = "✅"
        status_class = "complete"
    elif is_unlocked:
        icon = "📂"
        status_class = "active"
    else:
        icon = "🔒"
        status_class = "locked"

    st.markdown(
        f'<div class="step-card {status_class}">'
        f'<strong>{icon} Step 5: Runner Notepad</strong>'
        f'<br><span style="color:#666;font-size:0.85rem">'
        f'Delivery runner\'s handwritten records. Upload a file or enter manually.</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    if state['done']:
        result = state['result']
        if result:
            cols = st.columns(3)
            cols[0].metric("Total Rows", result.get('total', '-'))
            cols[1].metric("Imported", result.get('imported', '-'))
            cols[2].metric("Errors", result.get('errors', 0))
        return

    if not is_unlocked:
        st.caption("⏳ Complete the CRM Sales import first")
        return

    _init_notepad_entries()

    tab_upload, tab_manual = st.tabs(["📁 Upload File", "✍️ Manual Entry"])

    # ── Tab 1: File Upload ──
    with tab_upload:
        uploaded_files = st.file_uploader("Upload Notepad Excel/CSV (Multiple allowed)", type=['csv', 'xlsx', 'xls'], key="upload_notepad", accept_multiple_files=True)
        if uploaded_files:
            for uf in uploaded_files:
                valid, msg = validate_upload(uf)
                if not valid:
                    st.error(f"{uf.name}: {msg}")
                    return

            first_file = uploaded_files[0]
            sheet_option = None
            selected_sheet = 0  # default: first sheet

            if len(uploaded_files) == 1 and first_file.name.endswith(('.xlsx', '.xls')):
                try:
                    xl = pd.ExcelFile(first_file)
                    sheet_names = xl.sheet_names
                    first_file.seek(0)

                    if len(sheet_names) > 1:
                        st.info(f"📑 This file has **{len(sheet_names)} sheets**: {', '.join(sheet_names)}")
                        selected_sheets = st.multiselect(
                            "Select sheets to import",
                            sheet_names,
                            default=[sheet_names[0]],
                            key="np_sheet_select"
                        )
                        if selected_sheets:
                            selected_sheet = selected_sheets if len(selected_sheets) > 1 else selected_sheets[0]
                        else:
                            st.warning("Please select at least one sheet")
                            selected_sheet = None
                except Exception:
                    pass  # Fall through to default (first sheet)

            with st.expander(f"📋 Preview first 5 rows ({first_file.name})", expanded=False):
                try:
                    if first_file.name.endswith('.csv'):
                        preview = pd.read_csv(first_file, nrows=5)
                    else:
                        preview_sheet = selected_sheet if (selected_sheet is not None and selected_sheet != '__all__') else 0
                        
                        # handle if selected_sheet is a list (multiselect)
                        if isinstance(preview_sheet, list) and len(preview_sheet) > 0:
                            preview_sheet = preview_sheet[0]

                        preview = pd.read_excel(first_file, sheet_name=preview_sheet, nrows=5)
                    st.dataframe(preview.astype(str), width='stretch')
                    first_file.seek(0)
                except Exception:
                    st.warning("Could not preview file")

            if st.button(f"🚀 Import {len(uploaded_files)} Notepad File(s)", key="btn_notepad_file"):
                with st.spinner("Importing Notepad data..."):
                    importer = NotepadImporter(session_db)
                    total_res = {'total': 0, 'imported': 0, 'errors': 0}
                    all_ok = True
                    for uf in uploaded_files:
                        ok, result = safe_import(importer, uf, sheet_name=selected_sheet)
                        if ok and isinstance(result, dict):
                            total_res['total'] += result.get('total', 0)
                            total_res['imported'] += result.get('imported', 0)
                            total_res['errors'] += result.get('errors', 0)
                        else:
                            st.error(f"❌ Import failed for {uf.name}: {result}")
                            all_ok = False
                            break
                    if all_ok:
                        st.session_state.imports['notepad'] = {'done': True, 'result': total_res}
                        st.success(f"✅ All {len(uploaded_files)} Notepad file(s) imported!")
                        st.rerun()

    # ── Tab 2: Manual Entry ──
    with tab_manual:
        st.caption("Enter each order's delivery details. Click **Add Order Details** for more rows.")

        # ── Add new entry form ──
        with st.expander("➕ Add Order Details", expanded=len(st.session_state.notepad_entries) == 0):
            col1, col2 = st.columns(2)
            with col1:
                entry_date = st.date_input("Delivery Date", value=date.today(), key="np_date")
                entry_customer = st.text_input("Customer Name (optional)", key="np_customer")
                entry_order = st.text_input("Order Number", key="np_order",
                                           placeholder="e.g. T697")
                entry_runner = st.text_input("Runner Name", key="np_runner")
            with col2:
                entry_amount = st.number_input("Amount Collected (₹)", min_value=0.0,
                                              step=10.0, key="np_amount")
                entry_mode = st.selectbox("Payment Mode", 
                                         ["Cash", "Google Pay", "Paytm", "Package", "Card", "Other"],
                                         key="np_mode")
                entry_notes = st.text_area("Notes (optional)", key="np_notes",
                                          placeholder="Any remarks...", height=68)

            if st.button("➕ Add Order Details", key="btn_add_notepad", type="primary"):
                if not entry_order:
                    st.error("Please enter an Order Number")
                else:
                    st.session_state.notepad_entries.append({
                        'delivery_date': entry_date,
                        'customer_name': entry_customer,
                        'order_number': entry_order,
                        'amount_collected': entry_amount,
                        'payment_mode': entry_mode,
                        'runner_name': entry_runner,
                        'notes': entry_notes,
                    })
                    st.success(f"Added entry for {entry_customer or entry_order}")
                    st.rerun()

        # ── Show queued entries ──
        entries = st.session_state.notepad_entries
        if entries:
            st.markdown(f"**📝 {len(entries)} entries queued:**")

            display_data = []
            for i, e in enumerate(entries):
                display_data.append({
                    '#': i + 1,
                    'Date': e['delivery_date'],
                    'Customer': e['customer_name'],
                    'Order #': e['order_number'] or '—',
                    'Amount': f"₹{e['amount_collected']:.0f}",
                    'Mode': e['payment_mode'],
                    'Runner': e['runner_name'] or '—',
                })
            st.dataframe(pd.DataFrame(display_data), width='stretch', hide_index=True)

            total_amount = sum(e['amount_collected'] for e in entries)
            st.info(f"**Total: ₹{total_amount:,.0f}** across {len(entries)} entries")

            # Clear / Save buttons
            col_save, col_clear = st.columns(2)
            with col_save:
                if st.button("💾 Save All Entries", key="btn_save_notepad", type="primary"):
                    with st.spinner("Saving entries..."):
                        try:
                            from src.models.deliveries import DeliveryEvent
                            from src.models.payments import PaymentEvent
                            from src.models.orders import Order

                            saved = 0
                            for e in entries:
                                # Link to order if order_number provided
                                order_id = None
                                if e['order_number']:
                                    order = session_db.query(Order).filter_by(
                                        order_number=e['order_number']
                                    ).first()
                                    if order:
                                        order_id = order.id

                                delivery = DeliveryEvent(
                                    order_id=order_id,
                                    source='notepad',
                                    delivery_date=e['delivery_date'],
                                    customer_name=e['customer_name'],
                                    amount_collected=e['amount_collected'],
                                    payment_mode=e['payment_mode'],
                                    runner_name=e['runner_name'],
                                    notes=e['notes'],
                                    raw_data=e
                                )
                                session_db.add(delivery)

                                if e['amount_collected'] > 0:
                                    payment = PaymentEvent(
                                        order_id=order_id,
                                        source='notepad',
                                        payment_date=e['delivery_date'],
                                        amount=e['amount_collected'],
                                        payment_mode=e['payment_mode'],
                                        original_mode=e['payment_mode'],
                                        raw_data=e
                                    )
                                    session_db.add(payment)

                                saved += 1

                            session_db.commit()
                            st.session_state.imports['notepad'] = {
                                'done': True,
                                'result': {'total': saved, 'imported': saved, 'errors': 0}
                            }
                            st.session_state.notepad_entries = []
                            st.success(f"✅ Saved {saved} entries!")
                            st.rerun()
                        except Exception as ex:
                            session_db.rollback()
                            st.error(f"❌ Save failed: {ex}")

            with col_clear:
                if st.button("🗑️ Clear All", key="btn_clear_notepad"):
                    st.session_state.notepad_entries = []
                    st.rerun()
        else:
            st.caption("No entries yet. Use the form above to add order details.")

# ── Cash Register Import Step ─────────────────────────────

def render_cash_register_step(session_db, is_unlocked):
    """Step 6: Cash Register — file upload with sheet selection."""
    should_render = render_step_card(
        6, "Cash Register",
        "Daily cash register entries for cash variance detection.",
        'cash_register', is_unlocked, session_db
    )

    if should_render is not True:
        return

    uploaded_files = st.file_uploader("Upload Cash Register Excel (Multiple allowed)", type=['xlsx', 'xls'], key="upload_cash_register", accept_multiple_files=True)
    if uploaded_files:
        for uf in uploaded_files:
            valid, msg = validate_upload(uf)
            if not valid:
                st.error(f"{uf.name}: {msg}")
                return

        first_file = uploaded_files[0]
        selected_sheet = 0  # default: first sheet
        
        if len(uploaded_files) == 1:
            try:
                xl = pd.ExcelFile(first_file)
                sheet_names = xl.sheet_names
                first_file.seek(0)

                if len(sheet_names) > 1:
                    st.info(f"📑 This file has **{len(sheet_names)} sheets**: {', '.join(sheet_names)}")
                    selected_sheets = st.multiselect(
                        "Select sheets to import",
                        sheet_names,
                        default=[sheet_names[0]],
                        key="cr_sheet_select"
                    )
                    if selected_sheets:
                        selected_sheet = selected_sheets if len(selected_sheets) > 1 else selected_sheets[0]
                    else:
                        st.warning("Please select at least one sheet")
                        return
            except Exception:
                pass  # Fall through to default (first sheet)

        with st.expander(f"📋 Preview first 5 rows ({first_file.name})", expanded=False):
            try:
                preview_sheet = selected_sheet if not isinstance(selected_sheet, list) else selected_sheet[0]
                preview = pd.read_excel(first_file, sheet_name=preview_sheet, nrows=5)
                st.dataframe(preview.astype(str), width='stretch')
                first_file.seek(0)
            except Exception:
                st.warning("Could not preview file")

        if st.button(f"🚀 Import {len(uploaded_files)} Cash Register File(s)", key="btn_cash_register"):
            with st.spinner(f"Importing Cash Register data..."):
                importer = CashRegisterImporter(session_db)
                total_res = {'total': 0, 'imported': 0, 'errors': 0}
                all_ok = True

                for uf in uploaded_files:
                    # If user selected multiple sheets, import each one separately
                    sheets_to_import = selected_sheet if isinstance(selected_sheet, list) else [selected_sheet]
                    for sheet in sheets_to_import:
                        uf.seek(0)
                        ok, result = safe_import(importer, uf, sheet_name=sheet)
                        if ok and isinstance(result, dict):
                            total_res['total'] += result.get('total', 0)
                            total_res['imported'] += result.get('imported', 0)
                            total_res['errors'] += result.get('errors', 0)
                        else:
                            st.error(f"❌ Import failed for {uf.name} (sheet: {sheet}): {result}")
                            all_ok = False
                            break
                    if not all_ok:
                        break

                if all_ok:
                    st.session_state.imports['cash_register'] = {'done': True, 'result': total_res}
                    sheets_label = sheets_to_import if isinstance(selected_sheet, list) else [selected_sheet]
                    st.success(f"✅ Cash Register imported! Sheets: {', '.join(str(s) for s in sheets_label)}")
                    if total_res['errors'] > 0:
                        st.warning(f"⚠️ {total_res['errors']} rows had issues and were skipped")
                    st.rerun()


# ── Data Coverage Helper ─────────────────────────────────

def get_data_coverage(session_db):
    """
    Query the DB for the earliest and latest date covered by each import source.
    Returns a list of dicts with keys: source, label, earliest, latest, count.
    """
    from sqlalchemy import func
    from src.models.cash_register import CashRegisterEntry
    from src.models.expenses import Expense

    sources = []

    # CRM Sales (PaymentEvents from CRM)
    q = session_db.query(
        func.min(PaymentEvent.payment_date),
        func.max(PaymentEvent.payment_date),
        func.count(PaymentEvent.id)
    ).filter(PaymentEvent.source == 'crm').one()
    sources.append({'source': 'crm_sales', 'label': 'CRM Sales',
                    'earliest': q[0], 'latest': q[1], 'count': q[2]})

    # CRM Orders (Order records)
    q = session_db.query(
        func.min(Order.order_date),
        func.max(Order.order_date),
        func.count(Order.id)
    ).one()
    sources.append({'source': 'crm_orders', 'label': 'CRM Orders',
                    'earliest': q[0], 'latest': q[1], 'count': q[2]})

    # CRM Delivery (DeliveryEvents from CRM)
    q = session_db.query(
        func.min(DeliveryEvent.delivery_date),
        func.max(DeliveryEvent.delivery_date),
        func.count(DeliveryEvent.id)
    ).filter(DeliveryEvent.source == 'crm').one()
    sources.append({'source': 'crm_delivery', 'label': 'CRM Delivery',
                    'earliest': q[0], 'latest': q[1], 'count': q[2]})

    # MSWIPE (PaymentEvents from mswipe)
    q = session_db.query(
        func.min(PaymentEvent.payment_date),
        func.max(PaymentEvent.payment_date),
        func.count(PaymentEvent.id)
    ).filter(PaymentEvent.source == 'mswipe').one()
    sources.append({'source': 'mswipe', 'label': 'MSWIPE',
                    'earliest': q[0], 'latest': q[1], 'count': q[2]})

    # Notepad (DeliveryEvents from notepad)
    q = session_db.query(
        func.min(DeliveryEvent.delivery_date),
        func.max(DeliveryEvent.delivery_date),
        func.count(DeliveryEvent.id)
    ).filter(DeliveryEvent.source == 'notepad').one()
    sources.append({'source': 'notepad', 'label': 'Runner Notepad',
                    'earliest': q[0], 'latest': q[1], 'count': q[2]})

    # Cash Register — show last non-zero entry before today (ignores future template rows)
    today = date.today()
    q_cr_earliest = session_db.query(func.min(CashRegisterEntry.entry_date)).scalar()
    q_cr_latest = session_db.query(
        func.max(CashRegisterEntry.entry_date)
    ).filter(
        CashRegisterEntry.entry_date <= today,
        CashRegisterEntry.derived_cash_from_orders > 0
    ).scalar()
    q_cr_count = session_db.query(func.count(CashRegisterEntry.id)).scalar()
    sources.append({'source': 'cash_register', 'label': 'Cash Register',
                    'earliest': q_cr_earliest, 'latest': q_cr_latest, 'count': q_cr_count})

    # Expenses
    q = session_db.query(
        func.min(Expense.expense_date),
        func.max(Expense.expense_date),
        func.count(Expense.id)
    ).one()
    sources.append({'source': 'expenses', 'label': 'Expenses',
                    'earliest': q[0], 'latest': q[1], 'count': q[2]})

    return sources


# ── Page: Import Wizard ───────────────────────────────────

def page_import(session_db):
    st.header("📥 Import Wizard")

    init_import_state()
    done, total = get_import_progress()

    # Progress bar
    progress_pct = done / total if total > 0 else 0
    st.markdown(
        f'<div class="progress-container">'
        f'<div class="progress-bar" style="width:{progress_pct*100:.0f}%"></div>'
        f'</div>'
        f'<p style="text-align:center;color:#666;font-size:0.85rem">'
        f'Progress: {done}/{total} complete ({progress_pct*100:.0f}%)</p>',
        unsafe_allow_html=True
    )

    if done == total and total > 0:
        st.success("🎉 All imports complete!")
        def _nav_to_recon():
            st.session_state['nav_radio'] = "Run Reconciliation"
        
        st.button("▶️ Go to Run Reconciliation", type="primary", key="nav_to_recon", on_click=_nav_to_recon)

    # Reset button
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 Reset All", key="reset_imports"):
            st.session_state.imports = {
                k: {'done': False, 'result': None}
                for k in st.session_state.imports
            }
            st.rerun()

    st.divider()

    # ── Data Coverage Panel ───────────────────────────────────
    with st.expander("📊 Data Coverage — What's already in the DB", expanded=True):
        try:
            coverage = get_data_coverage(session_db)
            today = date.today()
            rows = []
            for s in coverage:
                earliest = str(s['earliest']) if s['earliest'] else '—'
                latest   = str(s['latest'])   if s['latest']   else '—'
                count    = s['count']
                if s['latest']:
                    days_ago = (today - s['latest']).days
                    gap = f"{days_ago}d ago" if days_ago > 0 else "Today"
                    status = '🔴' if days_ago > 14 else ('🟡' if days_ago > 7 else '🟢')
                else:
                    gap = 'No data'
                    status = '⚫'
                rows.append({
                    '': status,
                    'Source': s['label'],
                    'Earliest': earliest,
                    'Latest': latest,
                    'Records': count,
                    'Last Import': gap,
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.caption("🟢 Up to date  🟡 1–2 weeks old  🔴 Older than 2 weeks  ⚫ No data imported")

            # Identify any source lagging behind the most advanced source
            sources_with_data = [s for s in coverage if s['latest']]
            if sources_with_data:
                max_latest = max(s['latest'] for s in sources_with_data)
                lagging = [s for s in sources_with_data if (max_latest - s['latest']).days > 3]
                if lagging:
                    lagging_names = ', '.join(s['label'] for s in lagging)
                    st.warning(f"⚠️ These sources are lagging behind: **{lagging_names}** — consider re-importing up to **{max_latest}**")
                else:
                    st.success("✅ All sources are in sync.")
            else:
                st.info("No data has been imported yet. Start with Step 1: CRM Sales Report.")
        except Exception as e:
            st.info(f"Could not load coverage data: {e}")

    st.divider()

    sales_done = st.session_state.imports['crm_sales']['done']


    # Step 1: CRM Sales Report (required first)
    render_import_step(
        1, "CRM Sales Report",
        "Payment transactions with amounts, dates, and payment modes. This is required first.",
        'crm_sales', CRMImporter, session_db, is_unlocked=True
    )

    # Step 2: CRM Orders Report
    render_import_step(
        2, "CRM Orders Report",
        "Authoritative order data with Net Amount, Due Date, Order Status. Enriches data from Step 1.",
        'crm_orders', CRMOrdersImporter, session_db, is_unlocked=sales_done
    )

    # Step 3: CRM Delivery Report
    render_import_step(
        3, "CRM Delivery Report",
        "Delivery dates and piece counts. Enables late-payment detection.",
        'crm_delivery', CRMDeliveryImporter, session_db, is_unlocked=sales_done
    )

    # Step 4: MSWIPE Transactions
    render_import_step(
        4, "MSWIPE Transactions",
        "Card/UPI payment terminal data for cross-validation. Supports both CSV (settlement report) and XLSX (transaction report).",
        'mswipe', MSwipeImporter, session_db, is_unlocked=sales_done
    )

    # Step 5: Runner Notepad — dual mode
    render_notepad_step(session_db, is_unlocked=sales_done)

    # Step 6: Cash Register
    render_cash_register_step(session_db, is_unlocked=sales_done)

    # Step 7: Expenses
    render_import_step(
        7, "Expenses",
        "Business expenses (cash & online). Cash expenses adjust the cash register variance to avoid false fraud alerts.",
        'expenses', ExpensesImporter, session_db, is_unlocked=sales_done
    )

    # Step 8: Paytm Transactions
    from src.importers.paytm import PaytmImporter
    render_import_step(
        8, "Company Paytm QR",
        "Payments received via the company Paytm QR code. These are online payments alongside MSWIPE.",
        'paytm', PaytmImporter, session_db, is_unlocked=sales_done
    )


# ── Page: Run Reconciliation ──────────────────────────────

def page_reconciliation(session_db):
    st.header("⚙️ Reconciliation Engine")

    mode = st.radio("Mode", ["📅 Single Date", "📆 Date Range"], horizontal=True, key="recon_mode")

    if mode == "📅 Single Date":
        run_date = st.date_input("Select Date to Reconcile", value=date.today())

        if st.button("▶️ Start Reconciliation", type="primary"):
            success = False
            with st.status("Reconciling Data...", expanded=True) as status:
                try:
                    st.write("Running Matching Service...")
                    matcher = MatchingService(session_db)
                    match_stats = matcher.match_notepad_deliveries()
                    mswipe_stats = matcher.match_mswipe_payments()

                    st.write(f"Running Reconciliation for {run_date}...")
                    recon = ReconciliationService(session_db)
                    run = recon.run_reconciliation(run_date)

                    status.update(label="Reconciliation Complete!", state="complete", expanded=False)
                    success = True
                except LaundryReconcilerError as e:
                    status.update(label="Reconciliation Failed", state="error", expanded=False)
                    st.error(f"❌ Reconciliation Failed: {e}")
                except Exception as e:
                    status.update(label="Unexpected Error", state="error", expanded=False)
                    st.error(f"❌ Unexpected Error: {e}")

            if success:
                st.success(f"✅ Reconciliation Complete! Run ID: {run.id}")

                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Notepad Matches",
                           f"{match_stats.get('exact', 0) + match_stats.get('fuzzy', 0)}")
                col2.metric("MSWIPE Matches", str(mswipe_stats.get('matched', 0)))
                col3.metric("Exceptions", str(run.summary_stats.get('total_exceptions', 0)))
                col4.metric("⏰ Ageing Orders", str(run.summary_stats.get('ageing_order_exceptions', 0)))
                col5.metric("🕵️ Backdated", str(run.summary_stats.get('backdated_payment_exceptions', 0)))

                late = run.summary_stats.get('late_payment_exceptions', 0)
                if late > 0:
                    st.warning(f"⚠️ {late} late payment(s) detected")

                st.button("📊 View Results", key="nav_to_results_single",
                          on_click=navigate_to, args=("View Results",))

    else:
        # Date range mode
        col_start, col_end = st.columns(2)
        with col_start:
            start_date = st.date_input("Start Date", value=date(2025, 11, 1), key="recon_start")
        with col_end:
            end_date = st.date_input("End Date", value=date(2025, 11, 30), key="recon_end")

        if start_date > end_date:
            st.error("Start date must be before end date")
            return

        total_days = (end_date - start_date).days + 1
        st.info(f"📊 Will reconcile **{total_days} days** from {start_date} to {end_date}")

        if st.button("▶️ Start Range Reconciliation", type="primary"):
            success = False
            with st.status("Reconciling Data Range...", expanded=True) as status:
                try:
                    # Run matching first
                    st.write("Running Matching Service...")
                    matcher = MatchingService(session_db)
                    match_stats = matcher.match_notepad_deliveries()
                    mswipe_stats = matcher.match_mswipe_payments()

                    # Run range reconciliation with progress bar
                    progress_bar = st.progress(0, text="Starting reconciliation...")

                    def on_progress(current, total):
                        progress_bar.progress(current / total, text=f"Processing day {current}/{total}...")

                    recon = ReconciliationService(session_db)
                    totals = recon.run_reconciliation_range(start_date, end_date, progress_callback=on_progress)

                    progress_bar.progress(1.0, text="✅ Complete!")
                    status.update(label="Range Reconciliation Complete!", state="complete", expanded=False)
                    success = True
                except LaundryReconcilerError as e:
                    status.update(label="Reconciliation Failed", state="error", expanded=False)
                    st.error(f"❌ Reconciliation Failed: {e}")
                except Exception as e:
                    status.update(label="Unexpected Error", state="error", expanded=False)
                    st.error(f"❌ Unexpected Error: {e}")

            if success:
                # Show consolidated results
                st.success(f"✅ Range Reconciliation Complete!")

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Days Processed", totals['days_processed'])
                col2.metric("Days with Activity", totals['days_with_activity'])
                col3.metric("Total Exceptions", totals['total_exceptions'])
                col4.metric("Days with Exceptions", totals['days_with_exceptions'])

                st.divider()

                col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
                col_a.metric("Order Exceptions", totals['order_exceptions'])
                col_b.metric("Late Payments", totals['late_payment_exceptions'])
                col_c.metric("Day Exceptions", totals['day_exceptions'])
                col_d.metric("⏰ Ageing", totals['ageing_order_exceptions'])
                col_e.metric("🕵️ Backdated", totals['backdated_payment_exceptions'])
                col_f.metric("Matching",
                            f"{match_stats.get('exact', 0) + match_stats.get('fuzzy', 0)} notepad, "
                            f"{mswipe_stats.get('matched', 0)} mswipe")

                # Per-day breakdown table
                per_day = totals.get('per_day', [])
                if per_day:
                    with st.expander("📋 Per-Day Breakdown", expanded=False):
                        day_df = pd.DataFrame(per_day)
                        day_df['date'] = day_df['date'].astype(str)
                        # Highlight days with exceptions
                        st.dataframe(day_df, width='stretch')

                # Store range results in session state for the results page
                st.session_state['range_results'] = totals
                st.session_state['range_dates'] = (str(start_date), str(end_date))

                if st.button("📊 View Results", type="primary", key="nav_to_results_range"):
                    st.session_state['nav_radio'] = "View Results"
                    st.rerun()


# ── Period Summary (Monthly / Quarterly) ─────────────────

def _render_period_summary(session_db, view_mode: str):
    """Render Monthly or Quarterly period aggregation view."""
    from src.services.reconciliation import ReconciliationService
    from calendar import monthrange
    import datetime

    st.subheader(f"{'📊 Monthly' if 'Monthly' in view_mode else '📊 Quarterly'} Period Summary")
    st.caption(
        "Aggregates daily reconciliation data over the period. "
        "Day-level GPay/cash variances that cancel out within the period are shown as "
        "self-correcting. Persistent exceptions remain open at the end of the period."
    )

    today = date.today()

    if "Monthly" in view_mode:
        col_m, col_y = st.columns(2)
        month = col_m.selectbox("Month", list(range(1, 13)),
                                index=today.month - 1,
                                format_func=lambda m: date(2000, m, 1).strftime('%B'),
                                key="period_month")
        year  = col_y.number_input("Year", min_value=2020, max_value=today.year,
                                   value=today.year, key="period_year")
        _, last_day = monthrange(int(year), int(month))
        start_date = date(int(year), int(month), 1)
        end_date   = date(int(year), int(month), last_day)
        period_label = start_date.strftime('%B %Y')
    else:
        qtr_options = ['Q1 (Jan–Mar)', 'Q2 (Apr–Jun)', 'Q3 (Jul–Sep)', 'Q4 (Oct–Dec)']
        qtr_starts  = [(1,1), (4,1), (7,1), (10,1)]
        qtr_ends    = [(3,31),(6,30),(9,30),(12,31)]
        current_qtr = (today.month - 1) // 3
        col_q, col_y = st.columns(2)
        qtr_idx = col_q.selectbox("Quarter", list(range(4)), index=current_qtr,
                                  format_func=lambda i: qtr_options[i],
                                  key="period_qtr")
        year = col_y.number_input("Year", min_value=2020, max_value=today.year,
                                  value=today.year, key="period_year_q")
        sm, sd = qtr_starts[qtr_idx]
        em, ed = qtr_ends[qtr_idx]
        start_date  = date(int(year), sm, sd)
        end_date    = date(int(year), em, ed)
        period_label = f"{qtr_options[qtr_idx]} {int(year)}"

    if st.button(f"📊 Load {period_label} Summary", type="primary", key="load_period"):
        with st.spinner(f"Computing period summary for {period_label}..."):
            recon = ReconciliationService(session_db)
            summary = recon.get_period_summary(start_date, end_date)
            st.session_state['period_summary'] = summary
            st.session_state['period_label']   = period_label

    summary = st.session_state.get('period_summary')
    if not summary:
        st.info("Select a period and click Load to see the results.")
        return

    period_label = st.session_state.get('period_label', period_label)
    st.success(f"Showing period: **{period_label}** "
               f"({summary.get('runs_completed', 0)} days reconciled "
               f"of {summary.get('days_in_period', 0)})")

    st.divider()

    # ── Top-level metrics ──────────────────────────────────
    c1, c2, c3 = st.columns(3)
    c1.metric("📋 Active Orders",  summary.get('active_orders', 0), help="Total distinct orders touched during this period")
    c2.metric("⚠️ Total Exceptions", summary.get('total_exceptions', 0), help="Total exceptions generated before period netting")
    c3.metric("⚠️ Persistent", summary.get('persistent_exceptions_count', 0), help="Exceptions that remain open and unresolved at the end of the period")
    
    st.write("")
    
    c4, c5, c6, c7 = st.columns(4)
    c4.metric("🔄 Self-Correcting", summary.get('self_correcting_pairs', 0),
              help="Day-level cash/GPay variances that canceled each other out within this period")
    c5.metric("⏰ Ageing", summary.get('ageing_order_count', 0), help="Orders older than the threshold missing a delivery confirmation")
    c6.metric("🕵️ Backdated", summary.get('backdated_count', 0), help="Payments matched to historical discrepancies or delayed MSWIPE sweeps")
    c7.metric("💸 Cash Expenses", f"₹{summary.get('total_cash_expenses', 0):,.0f}",
              help="Total cash expenses for the period — these are added back to register totals when calculating variances")

    st.divider()

    # ── Payment variance netting ───────────────────────────
    st.subheader("💰 Period-Level Cash & GPay Variance")
    st.caption(
        "These aggregates are the most reliable fraud-detection view. "
        "Daily signals (like *SuspectedBackdatedCRMEntry*) can have false correlations — "
        "a register surplus on Day A might belong to a different order. "
        "But over the full period, every order's CRM payment and register deposit are both counted: "
        "if cash was legitimately deposited, the two sides cancel. "
        "**Only genuinely undeposited cash survives as a net residual in the CRM vs Register column.**"
    )

    st.write("")

    col_gpay, col_notepad_cash, col_crm_cash = st.columns(3)

    with col_gpay:
        st.subheader("💳 GPay")
        net_g = summary.get('net_gpay_variance', 0)
        st.metric("CRM GPay Total",  f"₹{summary.get('crm_gpay_total', 0):,.0f}")
        st.metric("MSWIPE Total",    f"₹{summary.get('mswipe_total', 0):,.0f}")
        color = "normal" if abs(net_g) <= 10 else "inverse"
        st.metric("Net Variance", f"₹{net_g:,.0f}", delta=f"₹{net_g:,.0f}",
                  delta_color=color)
        if abs(net_g) <= 10:
            st.success("✅ GPay within tolerance.")
        else:
            st.error(f"⚠️ Persistent GPay variance of ₹{net_g:,.0f}")

        gpay_drill = [ex for ex in summary.get('persistent_exceptions', [])
                      if ex.get('type') in ('GPayMismatch', 'GPayOrderMismatch', 'BackdatedGPayPayment')]
        if gpay_drill:
            with st.expander(f"🔍 {len(gpay_drill)} contributing exceptions", expanded=False):
                gp_rows = []
                for ex in gpay_drill:
                    ev = ex.get('evidence', {})
                    gp_rows.append({
                        'Date': ex.get('run_date', '—'),
                        'Type': ex.get('type', '—'),
                        'CRM GPay': f"₹{ev.get('crm_gpay', ev.get('crm_amount', 0)):,.0f}",
                        'MSWIPE': f"₹{ev.get('mswipe_gpay', ev.get('mswipe_amount', 0)):,.0f}",
                        'Diff': f"₹{ev.get('diff', ev.get('days_offset', 0)):,.0f}",
                        'Action': ex.get('action', '—'),
                    })
                st.dataframe(pd.DataFrame(gp_rows), width='stretch', hide_index=True)

    with col_notepad_cash:
        st.subheader("📋 Notepad vs Register")
        st.caption("Classic daily variance — runner notepad total vs cash register.")
        net_c = summary.get('net_cash_variance', 0)
        st.metric("Notepad Cash Total",  f"₹{summary.get('notepad_cash_total', 0):,.0f}")
        col_nc1, col_nc2 = st.columns(2)
        col_nc1.metric("Register Total", f"₹{summary.get('register_cash_total', 0):,.0f}")
        col_nc2.metric("Cash Expenses", f"₹{summary.get('total_cash_expenses', 0):,.0f}")
        color = "normal" if abs(net_c) <= 100 else "inverse"
        st.metric("Net Variance", f"₹{net_c:,.0f}", delta=f"₹{net_c:,.0f}",
                  delta_color=color)
        if abs(net_c) <= 100:
            st.success("✅ Notepad/Register within tolerance.")
        else:
            st.error(f"⚠️ Persistent variance of ₹{net_c:,.0f}")

        cash_drill = [ex for ex in summary.get('persistent_exceptions', [])
                      if ex.get('type') in (
                          'CashVariance', 'CashOrderNoRegister',
                          'SuspectedBackdatedCashPayment')]
        if cash_drill:
            with st.expander(f"🔍 {len(cash_drill)} contributing exceptions", expanded=False):
                cr_rows = []
                for ex in cash_drill:
                    ev = ex.get('evidence', {})
                    cr_rows.append({
                        'Date': ex.get('run_date', '—'),
                        'Type': ex.get('type', '—'),
                        'Expected': f"₹{ev.get('expected', ev.get('crm_amount', 0)):,.0f}",
                        'Actual': f"₹{ev.get('derived', 0):,.0f}",
                        'Diff': f"₹{ev.get('diff', 0):,.0f}",
                        'Action': ex.get('action', '—'),
                    })
                st.dataframe(pd.DataFrame(cr_rows), width='stretch', hide_index=True)

    with col_crm_cash:
        st.subheader("🚨 CRM vs Register")
        st.caption(
            "**Fraud detection view.** Compares what CRM says was collected in cash "
            "against what was actually deposited in the register over the full period. "
            "Daily false-positives cancel out here — only genuinely undeposited cash remains."
        )
        net_crm = summary.get('net_crm_vs_register_variance', 0)
        st.metric("CRM Cash Total",      f"₹{summary.get('crm_cash_total', 0):,.0f}")
        col_crm1, col_crm2 = st.columns(2)
        col_crm1.metric("Register Total", f"₹{summary.get('register_cash_total', 0):,.0f}")
        col_crm2.metric("Cash Expenses", f"₹{summary.get('total_cash_expenses', 0):,.0f}")
        tol = 100  # same as cash_variance_tolerance default
        color = "normal" if abs(net_crm) <= tol else "inverse"
        st.metric("Net Undeposited", f"₹{net_crm:,.0f}", delta=f"₹{net_crm:,.0f}",
                  delta_color=color)
        if abs(net_crm) <= tol:
            st.success("✅ All CRM cash accounted for in register.")
        elif net_crm > tol:
            st.error(
                f"🚨 ₹{net_crm:,.0f} collected per CRM was **never deposited** in the register "
                f"over this period. Investigate for pocketing."
            )
        else:
            st.warning(
                f"Register shows ₹{abs(net_crm):,.0f} more than CRM recorded — "
                f"possible cash deposited but not yet entered in CRM."
            )

        fraud_drill = [ex for ex in summary.get('persistent_exceptions', [])
                       if ex.get('type') in (
                           'CashUndeposited', 'SuspectedBackdatedCRMEntry')]
        if fraud_drill:
            with st.expander(f"🔍 {len(fraud_drill)} contributing exceptions", expanded=False):
                # ── Summary table ──────────────────────────────────
                fd_rows = []
                for ex in fraud_drill:
                    ev = ex.get('evidence', {})
                    fd_rows.append({
                        'Date': ex.get('run_date', '—'),
                        'Type': ex.get('type', '—'),
                        'CRM Cash': f"₹{ev.get('crm_cash_total', ev.get('crm_cash_amount', 0)):,.0f}",
                        'Register': f"₹{ev.get('register_cash_total', ev.get('register_on_crm_date', 0)):,.0f}",
                        'Gap': f"₹{ev.get('undeposited_amount', ev.get('crm_deficit', 0)):,.0f}",
                    })
                st.dataframe(pd.DataFrame(fd_rows), width='stretch', hide_index=True)

                st.divider()

                # ── Order-level breakdown per CashUndeposited date ──
                cash_undeposited = [ex for ex in fraud_drill if ex.get('type') == 'CashUndeposited']
                if cash_undeposited:
                    st.markdown("**🔎 Orders with CRM Cash payments on each flagged date:**")
                    st.caption(
                        "These are the orders that had cash marked received in CRM on the "
                        "date of the exception. One or more of these orders may have had their "
                        "cash pocketed rather than deposited. Cross-check with staff."
                    )
                    for ex in cash_undeposited:
                        ev = ex.get('evidence', {})
                        ex_date_str = ev.get('date', ex.get('run_date', ''))
                        gap = ev.get('undeposited_amount', 0)

                        try:
                            from datetime import date as _date
                            ex_date = _date.fromisoformat(str(ex_date_str))
                        except Exception:
                            ex_date = None

                        with st.expander(
                            f"📅 {ex_date_str} — ₹{gap:,.0f} undeposited — "
                            f"probable orders below",
                            expanded=True
                        ):
                            if ex_date is None:
                                st.warning("Could not parse exception date.")
                                continue

                            # Query all CRM cash payments on this date
                            crm_cash_on_date = session_db.query(PaymentEvent).filter(
                                PaymentEvent.source == 'crm',
                                PaymentEvent.payment_mode == 'Cash',
                                PaymentEvent.payment_date == ex_date,
                            ).all()

                            if not crm_cash_on_date:
                                st.info("No CRM cash payments found on this date.")
                                continue

                            order_rows = []
                            for p in crm_cash_on_date:
                                order = session_db.get(Order, p.order_id) if p.order_id else None
                                total_paid = sum(float(pp.amount) for pp in order.payments) if order else 0
                                balance = (float(order.order_amount) - total_paid) if order else 0
                                order_rows.append({
                                    'Order #': order.order_number if order else '—',
                                    'Customer': (order.customer_name or '—') if order else '—',
                                    'CRM Cash (this day)': f"₹{float(p.amount):,.0f}",
                                    'Order Total': f"₹{float(order.order_amount):,.0f}" if order else '—',
                                    'Total Paid': f"₹{total_paid:,.0f}",
                                    'Balance Due': f"₹{balance:,.0f}",
                                })

                            st.dataframe(pd.DataFrame(order_rows), width='stretch', hide_index=True)
                            st.caption(
                                f"Total CRM cash on {ex_date_str}: "
                                f"₹{sum(float(p.amount) for p in crm_cash_on_date):,.0f} across "
                                f"{len(crm_cash_on_date)} payment(s). "
                                f"Register gap: ₹{gap:,.0f}. "
                                "Investigate which order(s) did not have their cash deposited."
                            )

                # ── SuspectedBackdatedCRMEntry hint ────────────────
                backdated_crm = [ex for ex in fraud_drill if ex.get('type') == 'SuspectedBackdatedCRMEntry']
                if backdated_crm:
                    st.markdown("**🕵️ SuspectedBackdatedCRMEntry — cross-reference dates:**")
                    for ex in backdated_crm:
                        ev = ex.get('evidence', {})
                        st.info(
                            f"CRM date: **{ev.get('crm_recorded_date', '—')}** · "
                            f"Suspected actual collection: **{ev.get('suspected_collection_date', '—')}** · "
                            f"Register surplus on collection date: ₹{ev.get('register_surplus_on_that_date', 0):,.0f} · "
                            f"CRM deficit: ₹{ev.get('crm_deficit', 0):,.0f}  \n"
                            "If confirmed, correct the CRM payment date to the suspected collection date."
                        )

    st.divider()


    # ── Persistent exceptions table ────────────────────────
    persistent = summary.get('persistent_exceptions', [])
    if persistent:
        st.subheader(f"⚠️ Persistent Exceptions ({len(persistent)})")
        st.caption("These exceptions remain open even after period-level netting.")
        p_rows = []
        for ex in persistent:
            p_rows.append({
                'Date':     ex.get('run_date', '—'),
                'Type':     ex.get('type', '—'),
                'Severity': '🔴' if ex.get('severity') == 'high' else
                            '🟡' if ex.get('severity') == 'medium' else '🟢',
                'Action':   ex.get('action', '—'),
            })
        st.dataframe(pd.DataFrame(p_rows), width='stretch', hide_index=True)
    else:
        st.success("🎉 No persistent exceptions for this period!")

    # ── Per-day breakdown ──────────────────────────────────
    per_day = summary.get('per_day', [])
    if per_day:
        with st.expander("📋 Per-Day Breakdown", expanded=False):
            st.dataframe(pd.DataFrame(per_day), width='stretch', hide_index=True)



# ── Page: View Results ────────────────────────────────────

def page_results(session_db):
    st.header("📊 Reconciliation Dashboard")

    runs = session_db.query(ReconciliationRun).order_by(ReconciliationRun.run_date.desc()).all()
    if not runs:
        st.info("No reconciliation runs found. You need to run reconciliation first.")
        st.button("▶️ Go to Run Reconciliation", type="primary", key="nav_to_recon_empty_results",
                  on_click=navigate_to, args=("Run Reconciliation",))
        return

    # View mode selector — simplified to 2 modes
    view_mode = st.radio(
        "View Mode",
        ["📅 Single Day", "📆 Date Range"],
        horizontal=True, key="results_view_mode"
    )

    if view_mode == "📅 Single Day":
        run_options = {f"{r.run_date} (ID: {r.id})": r.id for r in runs}
        col_run, _ = st.columns([1, 2])
        selected_label = col_run.selectbox("Select Reconciliation Run", list(run_options.keys()))
        selected_id = run_options[selected_label]
        run = session_db.get(ReconciliationRun, selected_id)
        selected_runs = [run]
        run_ids = [selected_id]
        date_label = str(run.run_date)
    else:
        # Date range mode
        range_dates = st.session_state.get('range_dates', None)
        col_s, col_e = st.columns(2)
        with col_s:
            default_start = date.fromisoformat(range_dates[0]) if range_dates else date(2025, 11, 1)
            start_dt = st.date_input("Start Date", value=default_start, key="results_start")
        with col_e:
            default_end = date.fromisoformat(range_dates[1]) if range_dates else date(2025, 11, 30)
            end_dt = st.date_input("End Date", value=default_end, key="results_end")

        selected_runs = [r for r in runs if start_dt <= r.run_date <= end_dt]
        run_ids = [r.id for r in selected_runs]

        if start_dt.year == end_dt.year:
            date_label = f"{start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d, %Y')}"
        else:
            date_label = f"{start_dt.strftime('%b %d, %Y')} - {end_dt.strftime('%b %d, %Y')}"

        if not selected_runs:
            st.warning(f"No reconciliation runs found between {start_dt} and {end_dt}.")
            return

    st.divider()

    # ── Gather data for selected run(s) ──
    all_exceptions = session_db.query(OrderException).filter(
        OrderException.reconciliation_run_id.in_(run_ids)).all()

    # Deduplicate exceptions:
    # - Order-level: by (order_id, exception_type) — keep latest per order+type
    # - Day-level (order_id is None): by (run_id, exception_type) — keep each day's exception
    seen_ex = {}
    for e in all_exceptions:
        if e.order_id is not None:
            key = (e.order_id, e.exception_type)
        else:
            # Day-level exceptions: each run (= each day) is distinct
            key = (f"run_{e.reconciliation_run_id}", e.exception_type)
        if key not in seen_ex or (e.id > seen_ex[key].id):
            seen_ex[key] = e
    exceptions = list(seen_ex.values())

    # Reconciled orders across all selected runs
    order_ids = set()
    run_dates = [r.run_date for r in selected_runs]
    day_deliveries = session_db.query(DeliveryEvent).filter(
        DeliveryEvent.delivery_date.in_(run_dates)).all()
    day_payments = session_db.query(PaymentEvent).filter(
        PaymentEvent.payment_date.in_(run_dates)).all()

    # Deduplicate payments by ID (same payment shouldn't be counted twice)
    unique_payments = {p.id: p for p in day_payments}
    day_payments = list(unique_payments.values())
    # Build set of payment IDs in the selected date range for order-level filtering
    in_range_payment_ids = set(unique_payments.keys())

    for d in day_deliveries:
        if d.order_id:
            order_ids.add(d.order_id)
    for p in day_payments:
        if p.order_id:
            order_ids.add(p.order_id)
    recon_orders = session_db.query(Order).filter(Order.id.in_(order_ids)).all() if order_ids else []

    # Unmatched entries (global, not date-specific)
    unmatched_notepad = session_db.query(DeliveryEvent).filter(
        DeliveryEvent.source == 'notepad', DeliveryEvent.order_id == None).all()
    unmatched_mswipe = session_db.query(PaymentEvent).filter(
        PaymentEvent.source == 'mswipe', PaymentEvent.order_id == None).all()

    # Use first run for export compatibility, aggregate stats
    run = selected_runs[0]
    selected_id = run.id

    # ── Tabs (5 consolidated) ──
    tab_alerts, tab_overview, tab_exceptions, tab_explorer, tab_export = st.tabs([
        "🚨 Alerts", "📊 Overview", "📋 Exceptions",
        "🔍 Data Explorer", "📥 Export"
    ])

    # Helper: map run_id → run_date
    run_date_map = {r.id: r.run_date for r in selected_runs}

    # ══════════════════════════════════════════════════════
    # TAB 1: ALERTS — "What's wrong?"
    # ══════════════════════════════════════════════════════
    with tab_alerts:
        # ── Cash Fraud Alerts ──
        cash_fraud = [e for e in exceptions if e.exception_type == 'CashUndeposited']
        cash_variance = [e for e in exceptions if e.exception_type == 'CashVariance']
        if cash_fraud:
            st.error(f"🚨 **{len(cash_fraud)} Cash Fraud Alert(s)** — CRM cash was never deposited in the register.")
            
            def style_gap(val):
                try:
                    val_str = str(val).replace('₹', '').replace(',', '').replace('+', '')
                    numeric_val = float(val_str)
                    if numeric_val <= -10:
                        return 'color: #ff4b4b; font-weight: bold;'  # Red for shortfall
                    elif numeric_val >= 10:
                        return 'color: #00c04b; font-weight: bold;'  # Green for surplus
                except:
                    pass
                return ''

            fraud_rows = []
            for e in cash_fraud:
                ev = e.evidence or {}
                actual = float(ev.get('register_derived_cash', ev.get('register_cash_total', 0)))
                crm = float(ev.get('crm_cash_total', 0))
                gap_val = actual - crm
                
                if gap_val < 0:
                    formatted_gap = f"-₹{abs(gap_val):,.0f}"
                else:
                    formatted_gap = f"+₹{gap_val:,.0f}"

                fraud_rows.append({
                    'Date': str(run_date_map.get(e.reconciliation_run_id, '—')),
                    'CRM Cash': f"₹{crm:,.0f}",
                    'Register Derived': f"₹{actual:,.0f}",
                    'Gap': formatted_gap,
                })
            df_cash_fraud = pd.DataFrame(fraud_rows)
            st.dataframe(df_cash_fraud.style.applymap(style_gap, subset=['Gap']), width='stretch', hide_index=True)
            with st.expander("🔎 Drill down — orders with cash on flagged dates", expanded=False):
                for e in cash_fraud:
                    ev = e.evidence or {}
                    ex_date_str = ev.get('date', str(run_date_map.get(e.reconciliation_run_id, '')))
                    try:
                        from datetime import date as _date
                        ex_date = _date.fromisoformat(str(ex_date_str))
                    except Exception:
                        continue
                    crm_cash = session_db.query(PaymentEvent).filter(
                        PaymentEvent.source == 'crm', PaymentEvent.payment_mode == 'Cash',
                        PaymentEvent.payment_date == ex_date).all()
                    if not crm_cash:
                        continue
                    st.markdown(f"**📅 {ex_date_str}** — ₹{ev.get('undeposited_amount', 0):,.0f} undeposited")
                    st.dataframe(pd.DataFrame([{
                        'Order #': (session_db.get(Order, p.order_id).order_number if p.order_id else '—'),
                        'Customer': (session_db.get(Order, p.order_id).customer_name or '—') if p.order_id else '—',
                        'Cash Paid': f"₹{float(p.amount):,.0f}",
                    } for p in crm_cash]), width='stretch', hide_index=True)
        elif cash_variance:
            st.warning(f"💵 **{len(cash_variance)} Cash Variance(s)** — Notepad cash doesn't match Register.")
        else:
            st.success("✅ No cash issues detected.")
        st.divider()

        # ── GPay Mismatch ──
        gpay_alerts = [e for e in exceptions if e.exception_type == 'GPayMismatch']
        if gpay_alerts:
            st.warning(f"💳 **{len(gpay_alerts)} GPay Discrepancy(ies)**")
            gpay_rows = []
            for e in gpay_alerts:
                ev = e.evidence or {}
                actual = float(ev.get('mswipe_gpay', 0))
                crm = float(ev.get('crm_gpay', 0))
                gap_val = actual - crm
                
                if gap_val < 0:
                    formatted_gap = f"-₹{abs(gap_val):,.0f}"
                else:
                    formatted_gap = f"+₹{gap_val:,.0f}"

                gpay_rows.append({
                    'Date': str(run_date_map.get(e.reconciliation_run_id, '—')),
                    'CRM GPay': f"₹{crm:,.0f}",
                    'MSWIPE': f"₹{actual:,.0f}",
                    'Variance': formatted_gap,
                    'Severity': '🔴' if e.severity == 'high' else '🟡',
                })
            df_gpay = pd.DataFrame(gpay_rows)
            st.dataframe(df_gpay.style.applymap(style_gap, subset=['Variance']), width='stretch', hide_index=True)
        else:
            st.success("✅ GPay totals match MSWIPE.")
        st.divider()

        # ── Credit Policy Violations ──
        credit_alerts = [e for e in exceptions if e.exception_type == 'CreditPolicyViolation']
        if credit_alerts:
            st.error(f"💳 **{len(credit_alerts)} Credit Policy Violation(s)**")
            st.dataframe(pd.DataFrame([{
                'Order #': e.order.order_number if e.order else '—',
                'Customer': e.order.customer_name if e.order else '—',
                'Balance Due': f"₹{(e.evidence or {}).get('balance', (e.evidence or {}).get('outstanding', 0)):,.0f}",
            } for e in credit_alerts]), width='stretch', hide_index=True)
        else:
            st.success("✅ No credit policy violations.")
        st.divider()

        # ── Ageing Orders (collapsed) ──
        ageing_alerts = [e for e in exceptions if e.exception_type == 'AgeingOrder']
        if ageing_alerts:
            with st.expander(f"⏰ {len(ageing_alerts)} Ageing Order(s) — old orders with outstanding balance", expanded=False):
                ageing_rows = [{
                    'Order #': e.order.order_number if e.order else '—',
                    'Customer': e.order.customer_name if e.order else '—',
                    'Days Old': (e.evidence or {}).get('days_since_order', '—'),
                    'Balance': f"₹{(e.evidence or {}).get('balance', 0):,.0f}",
                } for e in sorted(ageing_alerts, key=lambda x: (x.evidence or {}).get('days_since_order', 0), reverse=True)]
                
                df_ageing = pd.DataFrame(ageing_rows)
                st.dataframe(df_ageing, width='stretch', hide_index=True)
                
                # Excel Export: Ageing orders
                import io
                buf_ageing = io.BytesIO()
                with pd.ExcelWriter(buf_ageing, engine='xlsxwriter') as ew:
                    df_ageing.to_excel(ew, sheet_name='Ageing_Orders', index=False)
                
                clean_date = date_label.replace(' ', '_').replace(',', '')
                st.download_button(
                    label="📥 Export Ageing Orders to Excel",
                    data=buf_ageing.getvalue(),
                    file_name=f"ageing_orders_{clean_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        # ── Backdated Detections (collapsed) ──
        bd_gpay = [e for e in exceptions if e.exception_type == 'BackdatedGPayPayment']
        bd_cash = [e for e in exceptions if e.exception_type == 'SuspectedBackdatedCashPayment']
        bd_crm = [e for e in exceptions if e.exception_type == 'SuspectedBackdatedCRMEntry']
        total_bd = len(bd_gpay) + len(bd_cash) + len(bd_crm)
        if total_bd > 0:
            with st.expander(f"🕵️ {total_bd} Backdated Detection(s) — informational", expanded=False):
                if bd_gpay:
                    st.caption("**GPay Backdated**")
                    st.dataframe(pd.DataFrame([{
                        'Order #': e.order.order_number if e.order else '—',
                        'Amount': f"₹{(e.evidence or {}).get('crm_amount', 0):,.0f}",
                        'CRM Date': (e.evidence or {}).get('crm_recorded_date', '—'),
                        'MSWIPE Date': (e.evidence or {}).get('mswipe_actual_date', '—'),
                    } for e in bd_gpay]), width='stretch', hide_index=True)
                if bd_cash:
                    st.caption("**Cash Backdated**")
                    st.dataframe(pd.DataFrame([{
                        'Deficit Date': (e.evidence or {}).get('deficit_date', '—'),
                        'Deficit': f"₹{(e.evidence or {}).get('deficit_amount', 0):,.0f}",
                        'Surplus Date': (e.evidence or {}).get('surplus_date', '—'),
                        'Surplus': f"₹{(e.evidence or {}).get('surplus_amount', 0):,.0f}",
                    } for e in bd_cash]), width='stretch', hide_index=True)
                if bd_crm:
                    st.caption("**CRM Backdated**")
                    st.dataframe(pd.DataFrame([{
                        'CRM Date': (e.evidence or {}).get('crm_recorded_date', '—'),
                        'Suspected Date': (e.evidence or {}).get('suspected_collection_date', '—'),
                        'Deficit': f"₹{(e.evidence or {}).get('crm_deficit', 0):,.0f}",
                    } for e in bd_crm]), width='stretch', hide_index=True)

    # ══════════════════════════════════════════════════════
    # TAB 2: Overview
    # ══════════════════════════════════════════════════════
    with tab_overview:
        total_ex = len(exceptions)
        high_ex = sum(1 for e in exceptions if e.severity == 'high')
        medium_ex = sum(1 for e in exceptions if e.severity == 'medium')
        low_ex = sum(1 for e in exceptions if e.severity in ('low', 'info'))
        row1 = st.columns(4)
        row1[0].metric("📅 Period", date_label)
        row1[1].metric("✅ Runs", str(len(selected_runs)))
        row1[2].metric("📋 Orders", str(len(recon_orders)))
        row1[3].metric("⚠️ Exceptions", str(total_ex))
        st.divider()
        col_sev, col_type = st.columns(2)
        with col_sev:
            st.subheader("Severity Breakdown")
            if total_ex > 0:
                sev_data = pd.DataFrame({'Severity': ['🔴 High', '🟡 Medium', '🟢 Low/Info'], 'Count': [high_ex, medium_ex, low_ex]})
                st.bar_chart(sev_data.set_index('Severity'), horizontal=True)
            else:
                st.success("No exceptions!")
        with col_type:
            st.subheader("Type Breakdown")
            if total_ex > 0:
                type_counts = {}
                for e in exceptions:
                    type_counts[e.exception_type] = type_counts.get(e.exception_type, 0) + 1
                st.dataframe(pd.DataFrame([{'Type': k, 'Count': v} for k, v in sorted(type_counts.items(), key=lambda x: -x[1])]), width='stretch', hide_index=True)
            else:
                st.success("No exceptions!")
        st.divider()
        st.subheader("💰 Grand Payment Summary — CRM vs Actuals")
        st.caption("Side-by-side comparison of what CRM says was collected vs what was actually received.")

        crm_payments_list = [p for p in day_payments if p.source == 'crm']
        mswipe_payments_list = [p for p in day_payments if p.source == 'mswipe']
        paytm_payments_list = [p for p in day_payments if p.source == 'paytm']
        notepad_payments_list = [p for p in day_payments if p.source == 'notepad']

        # ── CRM totals by mode ──
        crm_by_mode = {}
        for p in crm_payments_list:
            mode = p.payment_mode or 'Unknown'
            crm_by_mode[mode] = crm_by_mode.get(mode, 0) + float(p.amount)
        crm_total = sum(crm_by_mode.values())

        # ── Actual totals ──
        # Online: MSWIPE + Company Paytm
        mswipe_total = sum(float(p.amount) for p in mswipe_payments_list)
        paytm_total = sum(float(p.amount) for p in paytm_payments_list)
        online_actual_total = mswipe_total + paytm_total
        gpay_modes = {'Google Pay', 'GPay', 'UPI'}
        crm_gpay = sum(v for k, v in crm_by_mode.items() if k in gpay_modes)
        crm_paytm = sum(v for k, v in crm_by_mode.items() if k in ('Paytm', 'PhonePe'))

        # Cash: actual = register derived_cash_from_orders total
        from src.models.cash_register import CashRegisterEntry
        from src.models.bank_deposit import BankDeposit
        from src.models.package_transaction import PackageTransaction
        from sqlalchemy import func as sa_func
        register_cash_total = float(
            session_db.query(sa_func.sum(CashRegisterEntry.derived_cash_from_orders)).filter(
                CashRegisterEntry.entry_date.in_(run_dates),
            ).scalar() or 0.0
        )
        # Bank deposits for the period
        bank_deposit_total = float(
            session_db.query(sa_func.sum(BankDeposit.amount)).filter(
                BankDeposit.deposit_date.in_(run_dates),
            ).scalar() or 0.0
        )
        # Cash expenses for the period
        cash_expenses_total = float(
            session_db.query(sa_func.sum(Expense.amount)).filter(
                Expense.expense_date.in_(run_dates),
                Expense.mode == 'Cash',
            ).scalar() or 0.0
        )

        crm_cash = crm_by_mode.get('Cash', 0)
        crm_package = crm_by_mode.get('Package', 0)

        # ── Package purchase inflows (subtract from actuals) ──
        pkg_cash_total = float(
            session_db.query(sa_func.sum(PackageTransaction.amount)).filter(
                PackageTransaction.transaction_date.in_(run_dates),
                PackageTransaction.payment_mode == 'Cash',
            ).scalar() or 0.0
        )
        pkg_online_total = float(
            session_db.query(sa_func.sum(PackageTransaction.amount)).filter(
                PackageTransaction.transaction_date.in_(run_dates),
                PackageTransaction.payment_mode == 'Online',
            ).scalar() or 0.0
        )
        pkg_total = pkg_cash_total + pkg_online_total

        # Adjusted actuals (orders only, packages subtracted)
        register_orders_only = register_cash_total - pkg_cash_total
        online_orders_only = online_actual_total - pkg_online_total

        # ── Outstanding orders (30+ days old, balance > 0, IN RANGE) ──
        from datetime import timedelta
        if run_dates:
            earliest_date = min(run_dates)
            latest_date = max(run_dates)
            cutoff_30d = latest_date - timedelta(days=30)
            outstanding_orders = session_db.query(Order).filter(
                Order.order_date >= earliest_date,
                Order.order_date <= cutoff_30d,
                Order.balance > 0,
            ).all()
            outstanding_total = sum(float(o.balance) for o in outstanding_orders)
            outstanding_count = len(outstanding_orders)
        else:
            outstanding_total = 0.0
            outstanding_count = 0
            outstanding_orders = []

        # ── Header metrics ──
        # FRAUD VECTORS: Cash, GPay/UPI, Card — staff can manually mark
        # these in CRM. Verified against Register (cash) and MSWIPE (online).
        # SAFE (auto-recorded): Paytm (QR scan), Package (wallet deduction).
        cash_gap = register_orders_only - crm_cash

        # GPay/UPI/Card: staff-entered → verify against MSWIPE
        crm_gpay_card = crm_gpay  # GPay/UPI modes
        crm_card = sum(v for k, v in crm_by_mode.items() if k in ('Card',))
        crm_staff_online = crm_gpay_card + crm_card  # all staff-entered online
        # Paytm: auto-recorded in CRM — separate from fraud analysis
        crm_paytm_auto = crm_paytm  # Paytm/PhonePe modes auto-entered

        # MSWIPE covers GPay/UPI/Card actuals (NOT Paytm — that's separate)
        mswipe_orders_only = mswipe_total - pkg_online_total
        online_fraud_gap = mswipe_orders_only - crm_staff_online

        # Paytm recon: CRM Paytm vs Paytm QR data (informational only)
        paytm_recon_gap = paytm_total - crm_paytm_auto

        total_fraud_gap = cash_gap + online_fraud_gap

        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        col_h1.metric(
            "🚨 Cash Risk",
            f"₹{abs(cash_gap):,.0f}" if cash_gap < -100 else "✅",
            delta=f"Gap: ₹{cash_gap:,.0f}",
            delta_color="normal",
        )
        col_h2.metric(
            "🚨 Online Risk",
            f"₹{abs(online_fraud_gap):,.0f}" if online_fraud_gap < -100 else "✅",
            delta=f"Gap: ₹{online_fraud_gap:,.0f}",
            delta_color="normal",
        )
        col_h3.metric(
            "🚨 Total Fraud Risk",
            f"₹{abs(total_fraud_gap):,.0f}" if total_fraud_gap < -100 else "✅",
            delta=f"Gap: ₹{total_fraud_gap:,.0f}",
            delta_color="normal",
        )
        col_h4.metric(
            "⚠️ Unpaid 30d+",
            f"₹{outstanding_total:,.0f}",
            delta=f"{outstanding_count} orders",
            delta_color="inverse" if outstanding_count > 0 else "off",
        )

        # ── Side-by-side comparison table ──
        st.markdown("##### 🚨 Fraud Vectors (staff can manually mark)")
        fraud_rows = []

        def style_gap(val):
            try:
                numeric_val = float(str(val).replace('₹', '').replace(',', ''))
                if numeric_val < -100:
                    return 'color: #ff4b4b; font-weight: bold;'  # Shortfall (Red)
                elif numeric_val > 100:
                    return 'color: #00c04b; font-weight: bold;'  # Surplus (Green)
            except:
                pass
            return ''

        # Row 1: Cash
        fraud_rows.append({
            'Category': '💵 Cash',
            'CRM (staff-marked)': f'₹{crm_cash:,.0f}',
            'Actual': f'₹{register_orders_only:,.0f}',
            'Actual Source': f'Reg ₹{register_cash_total:,.0f} - Pkg ₹{pkg_cash_total:,.0f}',
            'Gap': f'₹{cash_gap:,.0f}',
            'Risk': '🔴' if cash_gap < -100 else ('🟡' if cash_gap > 100 else '✅'),
        })

        # Row 2: GPay/UPI/Card
        fraud_rows.append({
            'Category': '💳 GPay / UPI / Card',
            'CRM (staff-marked)': f'₹{crm_staff_online:,.0f}',
            'Actual': f'₹{mswipe_orders_only:,.0f}',
            'Actual Source': f'MSWIPE ₹{mswipe_total:,.0f} - Pkg ₹{pkg_online_total:,.0f}',
            'Gap': f'₹{online_fraud_gap:,.0f}',
            'Risk': '🔴' if online_fraud_gap < -100 else ('🟡' if online_fraud_gap > 100 else '✅'),
        })

        # Row 3: Fraud total
        fraud_rows.append({
            'Category': '🚨 TOTAL FRAUD RISK',
            'CRM (staff-marked)': f'₹{crm_cash + crm_staff_online:,.0f}',
            'Actual': f'₹{register_orders_only + mswipe_orders_only:,.0f}',
            'Actual Source': '',
            'Gap': f'₹{total_fraud_gap:,.0f}',
            'Risk': '🔴' if total_fraud_gap < -100 else ('🟡' if total_fraud_gap > 100 else '✅'),
        })

        df_fraud = pd.DataFrame(fraud_rows)
        st.dataframe(df_fraud.style.applymap(style_gap, subset=['Gap']), width='stretch', hide_index=True)

        # ── Safe channels ──
        st.markdown("##### ✅ Auto-Recorded (no fraud possible)")
        safe_rows = []

        safe_rows.append({
            'Category': '📱 Paytm (QR auto-recorded)',
            'CRM (auto)': f'₹{crm_paytm_auto:,.0f}',
            'Actual (QR data)': f'₹{paytm_total:,.0f}',
            'Gap': f'₹{paytm_recon_gap:,.0f}',
            'Note': 'System-to-system match',
        })

        safe_rows.append({
            'Category': '📦 Package (wallet auto-deducted)',
            'CRM (auto)': f'₹{crm_package:,.0f}',
            'Actual (QR data)': f'Purchases: ₹{pkg_total:,.0f}',
            'Gap': '—',
            'Note': 'Wallet deduction, no cash movement',
        })

        df_safe = pd.DataFrame(safe_rows)
        st.dataframe(df_safe.style.applymap(style_gap, subset=['Gap']), width='stretch', hide_index=True)

        # ── Callouts ──
        if total_fraud_gap < -100:
            st.error(
                f"🚨 **₹{abs(total_fraud_gap):,.0f} fraud risk (shortfall)** — "
                f"Cash: ₹{cash_gap:,.0f} (CRM marked but not in register) · "
                f"Online: ₹{online_fraud_gap:,.0f} (CRM marked GPay/UPI/Card "
                f"but not in MSWIPE). Staff can manually mark these "
                f"payment modes in CRM."
            )
        elif total_fraud_gap > 100:
            st.warning(
                f"🟡 Actuals exceed CRM by ₹{total_fraud_gap:,.0f} (surplus) — "
                f"Register/MSWIPE received more than staff marked in CRM."
            )
        else:
            st.success("✅ Staff-marked payments align with actuals (within tolerance).")

        if abs(paytm_recon_gap) > 100:
            st.info(
                f"ℹ️ Paytm recon gap: ₹{paytm_recon_gap:,.0f} — "
                f"difference between CRM auto-recorded Paytm and QR "
                f"data. Not a fraud risk (both are system-generated)."
            )

        if outstanding_total > 100:
            st.warning(
                f"⚠️ **{outstanding_count} orders (₹{outstanding_total:,.0f}) "
                f"unpaid 30+ days** — could be genuinely unpaid or "
                f"staff collected cash but didn't mark it."
            )

        # ══════════════════════════════════════════════════════
        # DRILL-DOWN: Online Variance → Orders (GPay/UPI/Card only)
        # ══════════════════════════════════════════════════════
        with st.expander(
            f"💳 Drill Down: Online Fraud Gap (₹{online_fraud_gap:,.0f}) — GPay/UPI/Card vs MSWIPE",
            expanded=False
        ):
            st.caption(
                "Traces the GPay/UPI/Card gap to specific orders. "
                "Staff can manually mark these modes in CRM. "
                "Paytm is excluded (auto-recorded, no fraud risk)."
            )

            # CRM GPay/UPI/Card payments (staff-entered, fraud vector)
            # Paytm excluded — auto-recorded, no fraud risk
            fraud_online_modes = gpay_modes | {'Card'}
            crm_online_payments = [
                p for p in crm_payments_list
                if (p.payment_mode or '') in fraud_online_modes
            ]
            # MSWIPE payments
            mswipe_by_order = {}
            mswipe_unmatched = []
            for p in mswipe_payments_list:
                if p.order_id:
                    mswipe_by_order.setdefault(p.order_id, []).append(p)
                else:
                    mswipe_unmatched.append(p)

            # Find CRM online payments where no MSWIPE exists for the same order
            crm_unmatched = []
            crm_matched_with_diff = []
            for p in crm_online_payments:
                if p.order_id and p.order_id in mswipe_by_order:
                    # Has MSWIPE — check if amounts match
                    mswipe_amt = sum(float(m.amount) for m in mswipe_by_order[p.order_id])
                    crm_amt = float(p.amount)
                    if abs(crm_amt - mswipe_amt) > 2:
                        crm_matched_with_diff.append((p, crm_amt, mswipe_amt))
                elif p.order_id and p.order_id not in mswipe_by_order:
                    crm_unmatched.append(p)
                elif not p.order_id:
                    crm_unmatched.append(p)

            # Section 1: CRM online with no MSWIPE
            if crm_unmatched:
                st.markdown(f"**🔴 {len(crm_unmatched)} CRM online payments with NO MSWIPE receipt** (₹{sum(float(p.amount) for p in crm_unmatched):,.0f})")
                unmatched_rows = []
                for p in sorted(crm_unmatched, key=lambda x: float(x.amount), reverse=True):
                    order = session_db.get(Order, p.order_id) if p.order_id else None
                    unmatched_rows.append({
                        'Date': str(p.payment_date),
                        'Order #': order.order_number if order else '—',
                        'Customer': (order.customer_name or '—') if order else '—',
                        'Mode': p.payment_mode,
                        'CRM Amount': f"₹{float(p.amount):,.0f}",
                        'MSWIPE': '❌ Missing',
                    })
                df_unmatched_online = pd.DataFrame(unmatched_rows)
                st.dataframe(df_unmatched_online, width='stretch', hide_index=True)
            else:
                st.success("✅ All CRM online payments have matching MSWIPE receipts.")

            # Section 2: MSWIPE with no CRM order
            if mswipe_unmatched:
                st.markdown(f"**🟡 {len(mswipe_unmatched)} MSWIPE transactions not linked to any CRM order** (₹{sum(float(p.amount) for p in mswipe_unmatched):,.0f})")
                orphan_rows = []
                for p in sorted(mswipe_unmatched, key=lambda x: float(x.amount), reverse=True)[:50]:
                    orphan_rows.append({
                        'Date': str(p.payment_date),
                        'Amount': f"₹{float(p.amount):,.0f}",
                        'Mode': p.payment_mode or '—',
                        'Ref': (p.raw_data or {}).get('Txn ID', (p.raw_data or {}).get('txn_id', '—')),
                    })
                st.dataframe(pd.DataFrame(orphan_rows), width='stretch', hide_index=True)
                if len(mswipe_unmatched) > 50:
                    st.caption(f"Showing top 50 of {len(mswipe_unmatched)}")

            # Section 3: Matched but amounts differ
            if crm_matched_with_diff:
                st.markdown(f"**🟡 {len(crm_matched_with_diff)} orders with CRM ≠ MSWIPE amount**")
                diff_rows = []
                for p, crm_amt, msw_amt in sorted(crm_matched_with_diff, key=lambda x: abs(x[1]-x[2]), reverse=True)[:30]:
                    order = session_db.get(Order, p.order_id) if p.order_id else None
                    diff_rows.append({
                        'Order #': order.order_number if order else '—',
                        'Customer': (order.customer_name or '—') if order else '—',
                        'CRM Amount': f"₹{crm_amt:,.0f}",
                        'MSWIPE Amount': f"₹{msw_amt:,.0f}",
                        'Diff': f"₹{crm_amt - msw_amt:,.0f}",
                    })
                st.dataframe(pd.DataFrame(diff_rows), width='stretch', hide_index=True)

            # ── Excel Export: Online drill-down ──
            st.markdown("---")
            buf_online = io.BytesIO()
            with pd.ExcelWriter(buf_online, engine='xlsxwriter') as ew:
                if crm_unmatched:
                    pd.DataFrame(unmatched_rows).to_excel(ew, sheet_name='CRM_No_MSWIPE', index=False)
                if mswipe_unmatched:
                    pd.DataFrame(orphan_rows).to_excel(ew, sheet_name='MSWIPE_Unlinked', index=False)
                if crm_matched_with_diff:
                    pd.DataFrame(diff_rows).to_excel(ew, sheet_name='Amount_Mismatch', index=False)
                # Add a summary sheet
                pd.DataFrame([{
                    'Period': f"{earliest_date} to {latest_date}",
                    'CRM GPay/UPI/Card': f"{crm_staff_online:,.0f}",
                    'MSWIPE (adj)': f"{mswipe_orders_only:,.0f}",
                    'Online Fraud Gap': f"{online_fraud_gap:,.0f}",
                    'CRM No MSWIPE Count': len(crm_unmatched) if crm_unmatched else 0,
                    'MSWIPE Unlinked Count': len(mswipe_unmatched) if mswipe_unmatched else 0,
                }]).to_excel(ew, sheet_name='Summary', index=False)
            st.download_button(
                label="📥 Export Online Drill-Down to Excel",
                data=buf_online.getvalue(),
                file_name=f"online_fraud_drilldown_{earliest_date}_{latest_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        # ══════════════════════════════════════════════════════
        # DRILL-DOWN: Cash Variance → Orders
        # ══════════════════════════════════════════════════════
        with st.expander(
            f"💵 Drill Down: Cash Variance (₹{cash_gap:,.0f})",
            expanded=False
        ):
            st.caption(
                "Traces the cash gap to specific orders. Register totals "
                "are adjusted by subtracting package purchases paid via cash. "
                "Orders marked 'Cash paid' in CRM but NOT confirmed by the "
                "runner or register are the most suspicious."
            )

            # Pre-load package cash amounts per day
            pkg_cash_by_day = {}
            pkg_cash_txns = session_db.query(PackageTransaction).filter(
                PackageTransaction.transaction_date.in_(run_dates),
                PackageTransaction.payment_mode == 'Cash',
            ).all()
            for pt in pkg_cash_txns:
                pkg_cash_by_day[pt.transaction_date] = (
                    pkg_cash_by_day.get(pt.transaction_date, 0) + float(pt.amount)
                )

            # Build daily comparison (adjusted for package cash)
            daily_cash = []
            for rd in sorted(run_dates):
                day_crm_cash = sum(
                    float(p.amount) for p in crm_payments_list
                    if p.payment_mode == 'Cash' and p.payment_date == rd
                )
                reg = session_db.query(CashRegisterEntry).filter_by(entry_date=rd).first()
                day_register_raw = float(reg.derived_cash_from_orders or 0) if reg else 0.0
                day_pkg_cash = pkg_cash_by_day.get(rd, 0)
                day_register = day_register_raw - day_pkg_cash  # adjusted
                day_variance = day_crm_cash - day_register

                if abs(day_variance) > 100 or day_crm_cash > 0 or day_register_raw > 0:
                    daily_cash.append({
                        'date': rd,
                        'crm_cash': day_crm_cash,
                        'register_raw': day_register_raw,
                        'pkg_cash': day_pkg_cash,
                        'register': day_register,
                        'variance': day_variance,
                    })

            if daily_cash:
                # ── Tab 1: Daily summary ──────────────────────
                cash_tab_daily, cash_tab_orders = st.tabs([
                    "📅 Daily Summary", "🔍 Suspicious Orders (Call List)"
                ])

                with cash_tab_daily:
                    daily_rows = []
                    for d in daily_cash:
                        # Gap: positive = surplus (register > CRM), negative = shortfall (cash missing)
                        gap = -(d['variance'])  # flip: old was CRM-Register, now Register-CRM
                        daily_rows.append({
                            'Date': str(d['date']),
                            'CRM Cash': f"₹{d['crm_cash']:,.0f}",
                            'Register (raw)': f"₹{d['register_raw']:,.0f}",
                            '- Pkg': f"₹{d['pkg_cash']:,.0f}" if d['pkg_cash'] > 0 else '—',
                            'Register (adj)': f"₹{d['register']:,.0f}",
                            'Gap': gap,
                            'Flag': '🔴' if gap < -100 else ('🟢' if gap > 100 else '✅'),
                        })

                    df_daily = pd.DataFrame(daily_rows)

                    def _color_gap(val):
                        """Green for surplus, red for shortfall."""
                        if not isinstance(val, (int, float)):
                            return ''
                        if val < -100:
                            return 'color: #ff4444; font-weight: bold'
                        if val > 100:
                            return 'color: #22cc44; font-weight: bold'
                        return 'color: #888888'

                    styled = df_daily.style.applymap(
                        _color_gap, subset=['Gap']
                    ).format({'Gap': '₹{:,.0f}'})
                    st.dataframe(styled, width='stretch', hide_index=True)

                    deficit_count = sum(1 for d in daily_cash if d['variance'] > 100)
                    surplus_count = sum(1 for d in daily_cash if d['variance'] < -100)
                    ok_count = len(daily_cash) - deficit_count - surplus_count
                    st.caption(
                        f"🔴 {deficit_count} deficit day(s) · "
                        f"🟡 {surplus_count} surplus day(s) · "
                        f"✅ {ok_count} OK"
                    )

                # ── Tab 2: Suspicious orders (call list) ──────
                with cash_tab_orders:
                    st.markdown(
                        "**Orders below are CRM cash payments on days where "
                        "the register shows a deficit.** Cross-referenced with "
                        "notepad to flag orders the runner did NOT confirm receiving."
                    )

                    # Get all days with activity
                    all_active_dates = {d['date'] for d in daily_cash}
                    date_variance = {d['date']: d['variance'] for d in daily_cash}
                    deficit_dates = {d['date'] for d in daily_cash if d['variance'] > 100}

                    if not all_active_dates:
                        st.success("✅ No cash activity — nothing to investigate.")
                    else:
                        # Pre-load notepad payments by (date, order_id) for cross-ref
                        notepad_cash_set = set()
                        for p in day_payments:
                            if p.source == 'notepad' and (p.payment_mode or '').lower() == 'cash':
                                notepad_cash_set.add((p.payment_date, p.order_id))

                        # Cumulative running balance across the full period:
                        # A deficit on Day X is "persistent" only if the
                        # cumulative variance never recovers by end of period.
                        # If later surpluses offset it, it's a timing issue.
                        # ── Build raw candidate list first, then assign risk ──
                        # Collect all CRM cash payments with metadata
                        raw_candidates = []
                        for p in crm_payments_list:
                            if p.payment_mode != 'Cash':
                                continue
                            if p.payment_date not in all_active_dates:
                                continue

                            order = session_db.get(Order, p.order_id) if p.order_id else None
                            notepad_confirmed = (p.payment_date, p.order_id) in notepad_cash_set
                            day_var = date_variance.get(p.payment_date, 0)
                            register_deficit = day_var > 100

                            phone = ''
                            if order and order.raw_data:
                                phone = order.raw_data.get('Phone No.', order.raw_data.get('phone', ''))

                            raw_candidates.append({
                                'payment': p,
                                'order': order,
                                'notepad_confirmed': notepad_confirmed,
                                'day_var': day_var,
                                'register_deficit': register_deficit,
                                'amount': float(p.amount),
                                'phone': phone,
                            })

                        # ── Per-day capped risk assignment ──
                        # On each deficit day, only flag unconfirmed orders up to
                        # the day's deficit as 🔴 High. Beyond the deficit amount,
                        # they become 🟡 Excess (can't all be pocketed).
                        # This ensures High Risk total ≈ actual Cash Gap.
                        from collections import defaultdict
                        by_date = defaultdict(list)
                        for c in raw_candidates:
                            by_date[c['payment'].payment_date].append(c)

                        suspicious_rows = []
                        for dt, day_items in by_date.items():
                            day_var = date_variance.get(dt, 0)
                            day_deficit = max(day_var, 0)  # only positive = deficit

                            # Sort unconfirmed first (largest amount), then confirmed
                            unconfirmed = sorted(
                                [c for c in day_items if not c['notepad_confirmed']],
                                key=lambda c: -c['amount']
                            )
                            confirmed = [c for c in day_items if c['notepad_confirmed']]

                            # Assign risk to unconfirmed orders
                            high_budget = day_deficit  # how much 🔴 we can assign
                            for c in unconfirmed:
                                if c['register_deficit'] and high_budget > 0:
                                    risk = '🔴 High'
                                    high_budget -= c['amount']
                                elif c['register_deficit'] and high_budget <= 0:
                                    risk = '🟡 Excess'
                                elif not c['register_deficit']:
                                    risk = '🟡 Medium'
                                else:
                                    risk = '🟡 Medium'

                                suspicious_rows.append({
                                    'Date': str(dt),
                                    'Order #': c['order'].order_number if c['order'] else '—',
                                    'Customer': (c['order'].customer_name or '—') if c['order'] else '—',
                                    'Phone': str(c['phone']) if c['phone'] else '—',
                                    'Cash (CRM)': f"₹{c['amount']:,.0f}",
                                    'Notepad': '❌',
                                    'Register': '❌ Deficit' if c['register_deficit'] else '✅ OK',
                                    'Risk': risk,
                                    'Day Gap': -(day_var),
                                })

                            # Confirmed orders
                            for c in confirmed:
                                suspicious_rows.append({
                                    'Date': str(dt),
                                    'Order #': c['order'].order_number if c['order'] else '—',
                                    'Customer': (c['order'].customer_name or '—') if c['order'] else '—',
                                    'Phone': str(c['phone']) if c['phone'] else '—',
                                    'Cash (CRM)': f"₹{c['amount']:,.0f}",
                                    'Notepad': '✅',
                                    'Register': '❌ Deficit' if c['register_deficit'] else '✅ OK',
                                    'Risk': '🟢 Low',
                                    'Day Gap': -(day_var),
                                })

                        if suspicious_rows:
                            # Sort: high → excess → medium → low; by amount desc
                            risk_order = {'🔴 High': 0, '🟡 Excess': 1, '🟡 Medium': 2, '🟢 Low': 3}
                            suspicious_rows.sort(
                                key=lambda r: (
                                    risk_order.get(r['Risk'], 9),
                                    -int(r['Cash (CRM)'].replace('₹', '').replace(',', '')),
                                ),
                            )

                            # Summary metrics
                            high_risk = [r for r in suspicious_rows if r['Risk'] == '🔴 High']
                            excess_risk = [r for r in suspicious_rows if r['Risk'] == '🟡 Excess']
                            med_risk = [r for r in suspicious_rows if r['Risk'] == '🟡 Medium']
                            low_risk = [r for r in suspicious_rows if r['Risk'] == '🟢 Low']
                            high_total = sum(
                                int(r['Cash (CRM)'].replace('₹', '').replace(',', ''))
                                for r in high_risk
                            )
                            excess_total = sum(
                                int(r['Cash (CRM)'].replace('₹', '').replace(',', ''))
                                for r in excess_risk
                            )
                            med_total = sum(
                                int(r['Cash (CRM)'].replace('₹', '').replace(',', ''))
                                for r in med_risk
                            )
                            low_total = sum(
                                int(r['Cash (CRM)'].replace('₹', '').replace(',', ''))
                                for r in low_risk
                            )
                            all_listed_total = high_total + excess_total + med_total + low_total

                            col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
                            col_s1.metric(
                                "🚨 Cash Gap",
                                f"₹{cash_gap:,.0f}",
                                delta="NET missing",
                                delta_color="inverse" if cash_gap > 100 else "off",
                            )
                            col_s2.metric(
                                "🔴 High Risk",
                                str(len(high_risk)),
                                delta=f"₹{high_total:,}",
                                delta_color="inverse",
                            )
                            col_s3.metric(
                                "🟡 Excess/Medium",
                                str(len(excess_risk) + len(med_risk)),
                                delta=f"₹{excess_total + med_total:,}" if (excess_total + med_total) else None,
                                delta_color="off",
                            )
                            col_s4.metric("🟢 Confirmed", str(len(low_risk)))
                            col_s5.metric("All Orders", str(len(suspicious_rows)),
                                          delta=f"₹{all_listed_total:,}")

                            df_suspicious = pd.DataFrame(suspicious_rows)

                            def _color_day_gap(val):
                                if not isinstance(val, (int, float)):
                                    return ''
                                if val < -100:
                                    return 'color: #ff4444; font-weight: bold'
                                if val > 100:
                                    return 'color: #22cc44; font-weight: bold'
                                return 'color: #888888'

                            styled_sus = df_suspicious.style.applymap(
                                _color_day_gap, subset=['Day Gap']
                            ).format({'Day Gap': '₹{:,.0f}'})
                            st.dataframe(
                                styled_sus,
                                width='stretch', hide_index=True,
                            )
                            st.caption(
                                "**🔴 High**: No notepad + on a deficit day, "
                                "capped at day's deficit (these orders "
                                "account for the missing cash — investigate). · "
                                "**🟡 Excess**: No notepad + deficit day, "
                                "but beyond the day's gap (can't all be "
                                "pocketed since register proves partial deposit). · "
                                "**🟡 Medium**: No notepad but register OK. · "
                                "**🟢 Low**: Runner confirmed."
                            )

                            # ── Excel Export: Cash drill-down ──
                            buf_cash = io.BytesIO()
                            with pd.ExcelWriter(buf_cash, engine='xlsxwriter') as ew:
                                df_suspicious.to_excel(ew, sheet_name='Suspicious_Orders', index=False)
                                pd.DataFrame(daily_rows).to_excel(ew, sheet_name='Daily_Summary', index=False)
                                # High risk only sheet for quick action
                                if high_risk:
                                    pd.DataFrame(high_risk).to_excel(ew, sheet_name='High_Risk_Only', index=False)
                                # Summary sheet
                                pd.DataFrame([{
                                    'Period': f"{earliest_date} to {latest_date}",
                                    'CRM Cash': f"{crm_cash:,.0f}",
                                    'Register (adj)': f"{register_orders_only:,.0f}",
                                    'Cash Gap': f"{cash_gap:,.0f}",
                                    'High Risk Orders': len(high_risk),
                                    'High Risk Amount': f"{high_total:,}",
                                    'Excess/Medium': len(excess_risk) + len(med_risk),
                                    'Low Risk (confirmed)': len(low_risk),
                                }]).to_excel(ew, sheet_name='Summary', index=False)
                            st.download_button(
                                label="📥 Export Cash Drill-Down to Excel",
                                data=buf_cash.getvalue(),
                                file_name=f"cash_fraud_drilldown_{earliest_date}_{latest_date}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                        else:
                            st.info("No CRM cash orders found in the selected period.")
            else:
                st.info("No cash activity in the selected period.")

        # ── Detailed CRM breakdown ──
        with st.expander("📊 Detailed CRM Breakdown by Mode", expanded=False):
            detail_rows = []
            _mode_icons = {'Cash': '💵', 'Google Pay': '💳', 'GPay': '💳', 'UPI': '💳',
                          'Paytm': '📱', 'PhonePe': '📱', 'Package': '📦', 'Card': '💳',
                          'Online': '🌐', 'Advance': '⏩', 'Due': '⏳'}
            for mode in sorted(crm_by_mode.keys()):
                icon = _mode_icons.get(mode, '🔹')
                detail_rows.append({
                    'Mode': f"{icon} {mode}",
                    'CRM Amount': f"₹{crm_by_mode[mode]:,.0f}",
                    'Transactions': sum(1 for p in crm_payments_list if (p.payment_mode or 'Unknown') == mode),
                })
            st.dataframe(pd.DataFrame(detail_rows), width='stretch', hide_index=True)

        # ── Cash flow breakdown ──
        with st.expander("🏦 Cash Flow Details", expanded=False):
            st.markdown(f"""
            | Item | Amount |
            |---|---|
            | Register derived cash (orders) | ₹{register_cash_total:,.0f} |
            | Cash expenses (already in derived) | ₹{cash_expenses_total:,.0f} |
            | Bank deposits (already in derived) | ₹{bank_deposit_total:,.0f} |
            """)

    # ══════════════════════════════════════════════════════
    # TAB 3: Exceptions Queue (simplified filters)
    # ══════════════════════════════════════════════════════
    with tab_exceptions:
        st.subheader("📋 Exceptions List")
        with st.expander("ℹ️ Exception Types Guide", expanded=False):
            st.markdown("Here is what each exception type means:")
            for ex_type, desc in EXCEPTION_DESCRIPTIONS.items():
                st.markdown(f"- **{ex_type}**: {desc}")
        
        if exceptions:
            # Collapsible filter panel
            with st.expander("🔧 Filters", expanded=False):
                col_f1, col_f2, col_f3 = st.columns(3)
                severities = sorted(set(e.severity for e in exceptions))
                filter_severity = col_f1.multiselect("Severity", severities, default=severities, key="dash_filter_sev")
                types = sorted(set(e.exception_type for e in exceptions))
                filter_type = col_f2.multiselect("Type", types, default=types, key="dash_filter_type")
                statuses = sorted(set(e.resolution_status for e in exceptions))
                filter_status = col_f3.multiselect("Status", statuses, default=statuses, key="dash_filter_status")

            ex_data = []
            for ex in exceptions:
                if (ex.severity in filter_severity and
                    ex.exception_type in filter_type and
                    ex.resolution_status in filter_status):
                    evidence_str = ''
                    if ex.evidence:
                        evidence_str = ', '.join(f"{k}: {v}" for k, v in ex.evidence.items() if k != 'raw_data')
                    order_num = ex.order.order_number if ex.order else 'Day-Level'
                    ex_date = run_date_map.get(ex.reconciliation_run_id, '—')
                    desc = EXCEPTION_DESCRIPTIONS.get(ex.exception_type, '')
                    rule_hint = desc.split('.')[0] + '.' if desc else '—'
                    ex_data.append({
                        'ID': ex.id,
                        'Date': str(ex_date),
                        'Order': order_num,
                        'Severity': '🔴' if ex.severity == 'high' else '🟡' if ex.severity == 'medium' else '🟢',
                        'Type': ex.exception_type,
                        'Rule': rule_hint,
                        'Evidence': evidence_str,
                        'Status': ex.resolution_status,
                    })

            if ex_data:
                # Render as HTML table to support native tooltips on the exception types
                html = "<table style='width:100%; border-collapse: collapse; font-size: 0.9em; margin-bottom: 1rem;'>"
                html += "<tr style='border-bottom: 2px solid #ddd; text-align: left;'>"
                html += "<th style='padding: 8px;'>ID</th><th style='padding: 8px;'>Date</th><th style='padding: 8px;'>Order</th>"
                html += "<th style='padding: 8px;'>Severity</th><th style='padding: 8px;'>Type</th><th style='padding: 8px;'>Rule</th>"
                html += "<th style='padding: 8px;'>Evidence</th><th style='padding: 8px;'>Status</th></tr>"
                
                for row in ex_data:
                    desc = EXCEPTION_DESCRIPTIONS.get(row['Type'], '').replace('"', '&quot;')
                    type_html = f'<span title="{desc}" style="cursor: help; border-bottom: 1px dotted #888; font-weight: bold;">{row["Type"]}</span>'
                    html += f"<tr style='border-bottom: 1px solid #eee;'>"
                    html += f"<td style='padding: 8px;'>{row['ID']}</td>"
                    html += f"<td style='padding: 8px;'>{row['Date']}</td>"
                    html += f"<td style='padding: 8px;'>{row['Order']}</td>"
                    html += f"<td style='padding: 8px;'>{row['Severity']}</td>"
                    html += f"<td style='padding: 8px;'>{type_html}</td>"
                    html += f"<td style='padding: 8px;'>{row['Rule']}</td>"
                    html += f"<td style='padding: 8px;'>{row['Evidence']}</td>"
                    html += f"<td style='padding: 8px;'>{row['Status']}</td>"
                    html += "</tr>"
                html += "</table>"
                
                st.markdown(html, unsafe_allow_html=True)
                st.caption(f"Showing {len(ex_data)} of {len(exceptions)} exceptions")

                # Resolution widget
                st.divider()
                st.subheader("Resolve Exception")
                ex_ids = [e['ID'] for e in ex_data]
                sel_id = st.selectbox("Select Exception ID", ex_ids, key="dash_resolve_id")
                sel_ex = next((e for e in ex_data if e['ID'] == sel_id), None)
                if sel_ex:
                    st.caption(f"**{sel_ex['Type']}** — {sel_ex['Order']} — {sel_ex['Evidence'][:80]}")
                resolution = st.radio("Action", ["resolved", "false_positive"], key="dash_resolve_act", horizontal=True)
                note = st.text_input("Resolution Note", key="dash_resolve_note")
                if st.button("✅ Resolve", key="dash_resolve_btn"):
                    ex_obj = session_db.get(OrderException, sel_id)
                    if ex_obj:
                        ex_obj.resolution_status = resolution
                        ex_obj.resolution_note = note
                        ex_obj.resolved_at = datetime.utcnow()
                        session_db.commit()
                        st.success(f"Exception {sel_id} marked as '{resolution}'")
                        st.rerun()
            else:
                st.info("No exceptions match the selected filters.")
        else:
            st.success("🎉 No exceptions found!")

    # ══════════════════════════════════════════════════════
    # TAB 4: Data Explorer (Orders + Cross-Source)
    # ══════════════════════════════════════════════════════
    with tab_explorer:
        st.subheader(f"Orders Active in {date_label}")
        search_order = st.text_input("🔍 Search by Order #", key="dash_exp_search_order").strip().lower()
        if recon_orders:
            orders_data = []
            if search_order:
                import rapidfuzz
            for o in recon_orders:
                if search_order:
                    # Exact prefix match OR fuzzy prefix match > 70
                    order_str = o.order_number.lower()
                    if not order_str.startswith(search_order):
                        # Compare against the prefix of the order string of the same length
                        prefix = order_str[:len(search_order)] if len(order_str) >= len(search_order) else order_str
                        score = rapidfuzz.fuzz.ratio(search_order, prefix)
                        if score < 70:
                            continue
                paid = sum(float(p.amount) for p in o.payments if p.id in in_range_payment_ids)
                excs = [e for e in exceptions if e.order_id == o.id]
                orders_data.append({
                    'Order #': o.order_number,
                    'Customer': o.customer_name or '—',
                    'Amount': f"₹{float(o.order_amount):,.0f}",
                    'Paid': f"₹{paid:,.0f}",
                    'Balance': f"₹{float(o.order_amount) - paid:,.0f}",
                    'Status': '⚠️' if excs else '✅',
                    'Issues': ', '.join(e.exception_type for e in excs) or '—'
                })
            st.dataframe(pd.DataFrame(orders_data), width='stretch', hide_index=True)
            total_ordered = sum(float(o.order_amount) for o in recon_orders)
            total_paid = sum(sum(float(p.amount) for p in o.payments if p.id in in_range_payment_ids) for o in recon_orders)
            st.caption(f"₹{total_ordered:,.0f} ordered · ₹{total_paid:,.0f} paid · ₹{total_ordered - total_paid:,.0f} outstanding")
        else:
            st.info("No orders found for this period.")
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                st.button("📥 Go to Import Data", on_click=navigate_to, args=("Import Data",), use_container_width=True, key="btn_exp_import")
            with col_btn2:
                st.button("▶️ Go to Run Reconciliation", on_click=navigate_to, args=("Run Reconciliation",), use_container_width=True, key="btn_exp_recon")

        st.divider()

        # Cross-Source Verification
        st.subheader("🔍 Cross-Source Payment Verification")
        cross_source_types = {
            'GPayOrderMismatch': '💳 GPay → No MSWIPE',
            'CashOrderNoRegister': '💵 Cash → No Register',
            'PaymentNotConfirmedByNotepad': '📋 Online → No Notepad',
            'NotepadPaymentNotInCRM': '📝 Notepad → No CRM',
        }
        cross_exceptions = [e for e in exceptions if e.exception_type in cross_source_types]
        if not cross_exceptions:
            st.success("✅ All payments confirmed across sources.")
        else:
            for exc_type, label in cross_source_types.items():
                grp = [e for e in cross_exceptions if e.exception_type == exc_type]
                if not grp:
                    continue
                with st.expander(f"{label} — **{len(grp)} order(s)**", expanded=False):
                    st.dataframe(pd.DataFrame([{
                        'Order #': e.order.order_number if e.order else '—',
                        'Amount': f"₹{(e.evidence or {}).get('crm_amount', (e.evidence or {}).get('notepad_amount', 0)):,.0f}",
                        'Mode': (e.evidence or {}).get('payment_mode', (e.evidence or {}).get('notepad_mode', '—')),
                        'Date': (e.evidence or {}).get('crm_date', (e.evidence or {}).get('notepad_date', '—')),
                    } for e in grp]), width='stretch', hide_index=True)

    # ══════════════════════════════════════════════════════
    # TAB 5: Export + Unmatched
    # ══════════════════════════════════════════════════════
    with tab_export:
        st.subheader("📥 Export to Excel")
        if st.button("📥 Generate Excel Report", key="dash_export_btn", type="primary"):
            with st.spinner("Generating report..."):
                exporter = ExcelExporter(session_db)
                output_file = f"report_{run.run_date}.xlsx"
                exporter.export_run(selected_id, output_file)
                with open(output_file, "rb") as f:
                    st.download_button(
                        label="📥 Download Excel Report", data=f,
                        file_name=output_file,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

        st.divider()

        # Unmatched entries
        col_np, col_ms = st.columns(2)
        with col_np:
            st.subheader("📝 Unmatched Notepad")
            if unmatched_notepad:
                st.dataframe(pd.DataFrame([{
                    'Date': d.delivery_date, 'Customer': d.customer_name or '—',
                    'Amount': f"₹{float(d.amount_collected or 0):,.0f}", 'Mode': d.payment_mode or '—',
                } for d in unmatched_notepad]), width='stretch', hide_index=True)
                st.caption(f"{len(unmatched_notepad)} unmatched")
            else:
                st.success("All matched!")
        with col_ms:
            st.subheader("💳 Unmatched MSWIPE")
            if unmatched_mswipe:
                st.dataframe(pd.DataFrame([{
                    'Date': p.payment_date, 'Amount': f"₹{float(p.amount):,.0f}",
                    'Ref': str(p.mswipe_ref_ids) if p.mswipe_ref_ids else '—',
                } for p in unmatched_mswipe]), width='stretch', hide_index=True)
                st.caption(f"{len(unmatched_mswipe)} unmatched")
            else:
                st.success("All matched!")

# ── Page: History ─────────────────────────────────────────

def page_history(session_db):
    st.header("📜 Reconciliation History")
    runs = session_db.query(ReconciliationRun).order_by(
        ReconciliationRun.run_date.desc()
    ).limit(50).all()

    if runs:
        history = []
        for r in runs:
            ex_count = session_db.query(OrderException).filter_by(reconciliation_run_id=r.id).count()
            history.append({
                'Run Date': r.run_date,
                'Status': r.status,
                'Exceptions': ex_count,
                'Started': r.started_at,
                'Completed': r.completed_at,
            })
        st.dataframe(pd.DataFrame(history), width='stretch')
    else:
        st.info("No reconciliation history yet.")
        st.button("▶️ Go to Run Reconciliation", type="primary", key="nav_to_recon_empty_history",
                  on_click=navigate_to, args=("Run Reconciliation",))


# ── Page: Order Lookup ────────────────────────────────────

def page_order_lookup(session_db):
    st.header("🔍 Order Lookup")
    st.caption(
        "Search by order number to see its complete history across all data sources: "
        "CRM Sales, CRM Orders, CRM Delivery, MSWIPE, Notepad, and any reconciliation exceptions."
    )

    # ── Search bar ──
    col_input, col_btn = st.columns([3, 1])
    with col_input:
        query = st.text_input(
            "Order Number",
            placeholder="e.g. T697 or partial like T69",
            key="order_lookup_query",
            label_visibility="collapsed",
        )
    with col_btn:
        do_search = st.button("🔍 Search", type="primary", key="order_lookup_btn", use_container_width=True)

    if not query and not do_search:
        st.info("Enter an order number above and press Search.")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            st.button("📥 Go to Import Data", on_click=navigate_to, args=("Import Data",), use_container_width=True)
        with col_btn2:
            st.button("▶️ Go to Run Reconciliation", on_click=navigate_to, args=("Run Reconciliation",), use_container_width=True)
        return

    if not query:
        st.warning("Please enter an order number to search.")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            st.button("📥 Go to Import Data", on_click=navigate_to, args=("Import Data",), use_container_width=True, key="btn_lookup_import_empty")
        with col_btn2:
            st.button("▶️ Go to Run Reconciliation", on_click=navigate_to, args=("Run Reconciliation",), use_container_width=True, key="btn_lookup_recon_empty")
        return

    # ── Find matching orders (exact first, then partial) ──
    from sqlalchemy import or_
    q = query.strip()
    orders = (
        session_db.query(Order)
        .filter(Order.order_number.ilike(f"%{q}%"))
        .order_by(Order.order_date.desc())
        .limit(20)
        .all()
    )

    if not orders:
        st.error(f"No orders found matching **'{q}'**. Try a shorter prefix or check the order number.")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            st.button("📥 Go to Import Data", on_click=navigate_to, args=("Import Data",), use_container_width=True, key="btn_lookup_import_notfound")
        with col_btn2:
            st.button("▶️ Go to Run Reconciliation", on_click=navigate_to, args=("Run Reconciliation",), use_container_width=True, key="btn_lookup_recon_notfound")
        return

    # ── If multiple matches, let user pick ──
    if len(orders) > 1:
        st.info(f"Found **{len(orders)}** orders matching **'{q}'**. Select one to view details.")
        order_options = {
            f"{o.order_number} — {o.customer_name or '?'} — ₹{float(o.order_amount):,.0f} ({o.order_date})": o.id
            for o in orders
        }
        selected_label = st.selectbox("Select Order", list(order_options.keys()), key="order_lookup_select")
        order = session_db.get(Order, order_options[selected_label])
    else:
        order = orders[0]

    if not order:
        st.error("Order not found.")
        return

    # ══════════════════════════════════════════════════════
    # ORDER HEADER CARD
    # ══════════════════════════════════════════════════════
    st.divider()

    # Compute quick stats
    total_paid_crm = sum(float(p.amount) for p in order.payments if p.source == 'crm')
    total_paid_mswipe = sum(float(p.amount) for p in order.payments if p.source == 'mswipe')
    total_paid_notepad = sum(float(d.amount_collected or 0) for d in order.deliveries if d.source == 'notepad')
    open_exceptions = [e for e in order.exceptions if e.resolution_status == 'open']
    crm_delivery = [d for d in order.deliveries if d.source == 'crm']
    notepad_delivery = [d for d in order.deliveries if d.source == 'notepad']

    # Header metrics
    content = f"""
<div style="background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:12px;padding:20px 24px;margin-bottom:16px;border:1px solid #0f3460;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
        <span style="font-size:1.8rem;">📦</span>
        <div>
            <h2 style="margin:0;color:#e2e8f0;font-size:1.4rem;">Order {order.order_number}</h2>
            <p style="margin:0;color:#94a3b8;font-size:0.9rem;">{order.customer_name or 'Unknown Customer'}{' · ' + str(order.customer_mobile) if order.customer_mobile else ''}</p>
        </div>
    </div>
</div>
"""
    st.markdown(content, unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🗓️ Order Date", str(order.order_date))
    c2.metric("💰 Order Amount", f"₹{float(order.order_amount):,.0f}")
    c3.metric("✅ Balance (CRM)", f"₹{float(order.balance):,.0f}")
    c4.metric("🚚 Deliveries", f"{len(crm_delivery)} CRM · {len(notepad_delivery)} Notepad")
    c5.metric(
        "⚠️ Open Exceptions",
        str(len(open_exceptions)),
        delta="needs attention" if open_exceptions else None,
        delta_color="inverse" if open_exceptions else "off",
    )

    st.divider()

    # ══════════════════════════════════════════════════════
    # TABS
    # ══════════════════════════════════════════════════════
    tab_crm, tab_crm_orders, tab_delivery, tab_mswipe, tab_notepad, tab_exceptions_tab = st.tabs([
        "🧾 CRM Sales", "📋 CRM Orders", "🚚 Delivery", "💳 MSWIPE", "📝 Notepad", "⚠️ Exceptions"
    ])

    # ── TAB 1: CRM Sales payments ──
    with tab_crm:
        st.subheader("CRM Sales — Payment Events")
        crm_payments = [p for p in order.payments if p.source == 'crm']
        if crm_payments:
            rows = []
            for p in sorted(crm_payments, key=lambda x: x.payment_date):
                rows.append({
                    'Date': str(p.payment_date),
                    'Amount': f"₹{float(p.amount):,.0f}",
                    'Mode': p.payment_mode or '—',
                    'Original Mode': p.original_mode or '—',
                    'Txn ID': p.online_txn_id or '—',
                    'Accept By': p.accept_by or '—',
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            total = sum(float(p.amount) for p in crm_payments)
            st.info(f"**{len(crm_payments)} payment event(s)** · Total collected: **₹{total:,.0f}**")
        else:
            st.warning("No CRM Sales payment events found for this order.")

        # Show raw_data from CRM Orders enrichment
        raw = order.raw_data or {}
        if raw:
            crm_meta_rows = []
            for k in ('Net Amount', 'Due Date', 'Pcs', 'Package', 'Status', 'Due Amount'):
                if k in raw:
                    crm_meta_rows.append({'Field': k, 'Value': str(raw[k])})
            if crm_meta_rows:
                st.divider()
                st.caption("📋 CRM Orders metadata attached to this order:")
                st.dataframe(pd.DataFrame(crm_meta_rows), use_container_width=True, hide_index=True)

    # ── TAB 2: CRM Orders enrichment ──
    with tab_crm_orders:
        st.subheader("CRM Orders — Authoritative Data")
        raw = order.raw_data or {}
        if raw:
            field_rows = []
            interesting_keys = [
                'Net Amount', 'Due Amount', 'Due Date', 'Pcs', 'Package',
                'Status', 'Order Status', 'Delivery Date', 'Delivered Pcs',
            ]
            # Show known interesting fields first, then any extras
            shown = set()
            for k in interesting_keys:
                if k in raw:
                    field_rows.append({'Field': k, 'Value': str(raw[k])})
                    shown.add(k)
            for k, v in raw.items():
                if k not in shown:
                    field_rows.append({'Field': k, 'Value': str(v)})
            st.dataframe(pd.DataFrame(field_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No CRM Orders data found for this order. Import the CRM Orders report to enrich it.")

        st.divider()
        st.caption("Core order record fields:")
        core_rows = [
            {'Field': 'Customer Code', 'Value': order.customer_code or '—'},
            {'Field': 'Customer Name', 'Value': order.customer_name or '—'},
            {'Field': 'Customer Address', 'Value': order.customer_address or '—'},
            {'Field': 'Customer Mobile', 'Value': order.customer_mobile or '—'},
            {'Field': 'Order Date', 'Value': str(order.order_date)},
            {'Field': 'Order Amount', 'Value': f"₹{float(order.order_amount):,.0f}"},
            {'Field': 'Payment Received (CRM)', 'Value': f"₹{float(order.payment_received):,.0f}"},
            {'Field': 'Adjustments', 'Value': f"₹{float(order.adjustments):,.0f}"},
            {'Field': 'Balance (CRM)', 'Value': f"₹{float(order.balance):,.0f}"},
            {'Field': 'Type', 'Value': order.type or '—'},
        ]
        st.dataframe(pd.DataFrame(core_rows), use_container_width=True, hide_index=True)

    # ── TAB 3: Delivery events ──
    with tab_delivery:
        st.subheader("Delivery Events")

        col_crm_del, col_np_del = st.columns(2)

        with col_crm_del:
            st.markdown("**📦 CRM Delivery**")
            if crm_delivery:
                crm_del_rows = []
                for d in sorted(crm_delivery, key=lambda x: x.delivery_date):
                    crm_del_rows.append({
                        'Delivery Date': str(d.delivery_date),
                        'Customer': d.customer_name or '—',
                        'Runner': d.runner_name or '—',
                        'Notes': d.notes or '—',
                    })
                st.dataframe(pd.DataFrame(crm_del_rows), use_container_width=True, hide_index=True)
            else:
                st.info("No CRM delivery records found.")
                st.caption("Import the CRM Delivery report to see delivery dates.")

        with col_np_del:
            st.markdown("**📝 Notepad Deliveries**")
            if notepad_delivery:
                np_del_rows = []
                for d in sorted(notepad_delivery, key=lambda x: x.delivery_date):
                    np_del_rows.append({
                        'Delivery Date': str(d.delivery_date),
                        'Customer': d.customer_name or '—',
                        'Amount Collected': f"₹{float(d.amount_collected or 0):,.0f}",
                        'Mode': d.payment_mode or '—',
                        'Runner': d.runner_name or '—',
                        'Notes': d.notes or '—',
                        'Confidence': f"{float(d.confidence_score or 0):.0%}" if d.confidence_score else 'Manual',
                    })
                st.dataframe(pd.DataFrame(np_del_rows), use_container_width=True, hide_index=True)
            else:
                st.info("No Notepad delivery records linked to this order.")

    # ── TAB 4: MSWIPE ──
    with tab_mswipe:
        st.subheader("MSWIPE — Card / UPI Transactions")
        mswipe_payments = [p for p in order.payments if p.source == 'mswipe']
        if mswipe_payments:
            ms_rows = []
            for p in sorted(mswipe_payments, key=lambda x: x.payment_date):
                ms_rows.append({
                    'Date': str(p.payment_date),
                    'Amount': f"₹{float(p.amount):,.0f}",
                    'Mode': p.original_mode or p.payment_mode or '—',
                    'Ref IDs': ', '.join(str(r) for r in (p.mswipe_ref_ids or [])) or '—',
                    'VPA': p.payee_vpa or '—',
                    'Confidence': f"{float(p.confidence_score or 0):.0%}" if p.confidence_score else '—',
                })
            st.dataframe(pd.DataFrame(ms_rows), use_container_width=True, hide_index=True)
            total_ms = sum(float(p.amount) for p in mswipe_payments)
            crm_gpay = sum(
                float(p.amount) for p in order.payments
                if p.source == 'crm' and (p.payment_mode or '').lower() in ('google pay', 'gpay', 'upi')
            )
            variance = crm_gpay - total_ms
            st.info(f"**{len(mswipe_payments)} MSWIPE transaction(s)** · Total: **₹{total_ms:,.0f}**")
            if crm_gpay > 0:
                color = "green" if abs(variance) <= 2 else "red"
                st.markdown(
                    f"CRM GPay: **₹{crm_gpay:,.0f}** — MSWIPE: **₹{total_ms:,.0f}** — "
                    f"<span style='color:{color}'>Variance: ₹{variance:,.0f}</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No MSWIPE transactions linked to this order.")
            st.caption(
                "MSWIPE entries are linked during the matching phase of reconciliation. "
                "Run reconciliation to establish links."
            )

    # ── TAB 5: Notepad payments ──
    with tab_notepad:
        st.subheader("Notepad — Runner Payment Records")
        notepad_payments = [p for p in order.payments if p.source == 'notepad']
        if notepad_payments or notepad_delivery:
            if notepad_payments:
                st.markdown("**💰 Notepad Payment Events**")
                np_pay_rows = []
                for p in sorted(notepad_payments, key=lambda x: x.payment_date):
                    np_pay_rows.append({
                        'Date': str(p.payment_date),
                        'Amount': f"₹{float(p.amount):,.0f}",
                        'Mode': p.payment_mode or '—',
                    })
                st.dataframe(pd.DataFrame(np_pay_rows), use_container_width=True, hide_index=True)
                total_np = sum(float(p.amount) for p in notepad_payments)
                st.info(f"**{len(notepad_payments)} notepad payment(s)** · Total: **₹{total_np:,.0f}**")
            else:
                st.info("No separate notepad payment events (delivery records may carry the amount).")
        else:
            st.info("No Notepad records linked to this order.")

    # ── TAB 6: Exceptions ──
    with tab_exceptions_tab:
        st.subheader("All Exceptions for This Order")
        all_excs = sorted(order.exceptions, key=lambda e: e.created_at, reverse=True)

        if not all_excs:
            st.success("🎉 No exceptions have ever been raised for this order!")
        else:
            open_excs = [e for e in all_excs if e.resolution_status == 'open']
            resolved_excs = [e for e in all_excs if e.resolution_status != 'open']

            if open_excs:
                st.error(f"🔴 **{len(open_excs)} open exception(s)** requiring attention")
            if resolved_excs:
                st.success(f"✅ {len(resolved_excs)} exception(s) resolved / false-positived")

            for e in all_excs:
                sev_icon = '🔴' if e.severity == 'high' else '🟡' if e.severity == 'medium' else '🟢'
                status_icon = '✅' if e.resolution_status == 'resolved' else \
                              '🚫' if e.resolution_status == 'false_positive' else '🔓'
                run_date = e.reconciliation_run.run_date if e.reconciliation_run else '—'

                with st.expander(
                    f"{sev_icon} {e.exception_type} — {status_icon} {e.resolution_status.upper()} "
                    f"(Run: {run_date})",
                    expanded=e.resolution_status == 'open'
                ):
                    cols = st.columns([2, 1, 1])
                    cols[0].markdown(f"**Suggested Action:** {e.suggested_action or '—'}")
                    cols[1].markdown(f"**Severity:** {sev_icon} {e.severity}")
                    cols[2].markdown(f"**Status:** {e.resolution_status}")

                    if e.evidence:
                        ev_rows = [
                            {'Key': k, 'Value': str(v)}
                            for k, v in e.evidence.items()
                            if k != 'raw_data'
                        ]
                        if ev_rows:
                            st.dataframe(pd.DataFrame(ev_rows), use_container_width=True, hide_index=True)

                    if e.resolution_note:
                        st.info(f"📝 Resolution note: {e.resolution_note}")

                    # Inline resolve widget for open exceptions
                    if e.resolution_status == 'open':
                        st.divider()
                        res_col1, res_col2, res_col3 = st.columns([2, 2, 1])
                        resolution = res_col1.radio(
                            "Action",
                            ["resolved", "false_positive"],
                            horizontal=True,
                            key=f"lookup_resolve_act_{e.id}"
                        )
                        note = res_col2.text_input("Note (optional)", key=f"lookup_resolve_note_{e.id}")
                        if res_col3.button("✅ Resolve", key=f"lookup_resolve_btn_{e.id}"):
                            e.resolution_status = resolution
                            e.resolution_note = note
                            e.resolved_at = datetime.utcnow()
                            session_db.commit()
                            st.success(f"Exception {e.id} marked as '{resolution}'")
                            st.rerun()


# ── Main App ──────────────────────────────────────────────

st.set_page_config(
    page_title="Digital Accountant",
    page_icon="🧺",
    layout="wide"
)

load_css()

st.title("🧺 Digital Accountant")

# Sidebar navigation
st.sidebar.title("Navigation")
pages = ["Import Data", "Run Reconciliation", "View Results", "Order Lookup", "History"]
page = st.sidebar.radio(
    "Go to",
    pages,
    label_visibility="collapsed",
    key="nav_radio"
)

session_db = get_session()

try:
    if page == "Import Data":
        page_import(session_db)
    elif page == "Run Reconciliation":
        page_reconciliation(session_db)
    elif page == "View Results":
        page_results(session_db)
    elif page == "Order Lookup":
        page_order_lookup(session_db)
    elif page == "History":
        page_history(session_db)
finally:
    session_db.close()
