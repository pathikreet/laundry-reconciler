"""
Laundry Reconciler — Streamlit UI

Guided import wizard + reconciliation dashboard.
Import order: CRM Sales → CRM Orders → CRM Delivery → MSWIPE → Notepad → Cash Register
"""
import streamlit as st
import pandas as pd
import os
import sys
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
from src.services.matching import MatchingService
from src.services.reconciliation import ReconciliationService
from src.exporters.excel_exporter import ExcelExporter
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent
from src.exceptions import LaundryReconcilerError

logger = logging.getLogger(__name__)

DB_PATH = "laundry_reconciler.db"
MAX_UPLOAD_MB = 50
ALLOWED_TYPES = ['csv', 'xlsx', 'xls']

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


def safe_import(importer, file_obj, suffix=".xlsx", **kwargs):
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
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
        }


def get_import_progress():
    """Return (completed, total) import step counts."""
    imports = st.session_state.get('imports', {})
    done = sum(1 for v in imports.values() if v.get('done'))
    return done, len(imports)


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

    file_types = file_types or ['csv', 'xlsx']
    uploaded = st.file_uploader(f"Upload {title}", type=file_types, key=f"upload_{key}")

    if uploaded:
        valid, msg = validate_upload(uploaded)
        if not valid:
            st.error(msg)
            return

        # Data preview
        with st.expander("📋 Preview first 5 rows", expanded=False):
            try:
                if uploaded.name.endswith('.csv'):
                    preview_df = pd.read_csv(uploaded, nrows=5)
                else:
                    preview_df = pd.read_excel(uploaded, nrows=5)
                st.dataframe(preview_df.astype(str), width='stretch')
                uploaded.seek(0)  # Reset for import
            except Exception:
                st.warning("Could not preview file")

        if st.button(f"🚀 Import {title}", key=f"btn_{key}"):
            with st.spinner(f"Importing {title}..."):
                importer = importer_class(session_db)
                kwargs = extra_kwargs or {}
                ok, result = safe_import(importer, uploaded, suffix=suffix)

                if ok:
                    st.session_state.imports[key] = {'done': True, 'result': result}
                    st.success(f"✅ {title} imported successfully!")
                    if result and result.get('errors', 0) > 0:
                        st.warning(f"⚠️ {result['errors']} rows had issues and were skipped")
                    st.rerun()
                else:
                    st.error(f"❌ Import failed: {result}")


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
        uploaded = st.file_uploader("Upload Notepad Excel/CSV", type=['csv', 'xlsx'], key="upload_notepad")
        if uploaded:
            valid, msg = validate_upload(uploaded)
            if not valid:
                st.error(msg)
            else:
                # Detect sheets for multi-tab Excel
                sheet_option = None
                selected_sheet = 0  # default: first sheet

                if uploaded.name.endswith(('.xlsx', '.xls')):
                    try:
                        xl = pd.ExcelFile(uploaded)
                        sheet_names = xl.sheet_names
                        uploaded.seek(0)

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

                with st.expander("📋 Preview first 5 rows", expanded=False):
                    try:
                        if uploaded.name.endswith('.csv'):
                            preview = pd.read_csv(uploaded, nrows=5)
                        else:
                            preview_sheet = selected_sheet if selected_sheet != '__all__' else 0
                            preview = pd.read_excel(uploaded, sheet_name=preview_sheet, nrows=5)
                        st.dataframe(preview.astype(str), width='stretch')
                        uploaded.seek(0)
                    except Exception:
                        st.warning("Could not preview file")

                if st.button("🚀 Import Notepad File", key="btn_notepad_file"):
                    with st.spinner("Importing Notepad data..."):
                        importer = NotepadImporter(session_db)
                        ok, result = safe_import(importer, uploaded, sheet_name=selected_sheet)
                        if ok:
                            st.session_state.imports['notepad'] = {'done': True, 'result': result}
                            st.success("✅ Notepad data imported!")
                            st.rerun()
                        else:
                            st.error(f"❌ Import failed: {result}")

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

    uploaded = st.file_uploader("Upload Cash Register Excel", type=['xlsx'], key="upload_cash_register")
    if uploaded:
        valid, msg = validate_upload(uploaded)
        if not valid:
            st.error(msg)
            return

        # Detect sheets for multi-tab Excel
        selected_sheet = 0  # default: first sheet
        try:
            xl = pd.ExcelFile(uploaded)
            sheet_names = xl.sheet_names
            uploaded.seek(0)

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

        with st.expander("📋 Preview first 5 rows", expanded=False):
            try:
                preview_sheet = selected_sheet if not isinstance(selected_sheet, list) else selected_sheet[0]
                preview = pd.read_excel(uploaded, sheet_name=preview_sheet, nrows=5)
                st.dataframe(preview.astype(str), width='stretch')
                uploaded.seek(0)
            except Exception:
                st.warning("Could not preview file")

        if st.button("🚀 Import Cash Register", key="btn_cash_register"):
            with st.spinner("Importing Cash Register data..."):
                importer = CashRegisterImporter(session_db)
                ok, result = safe_import(importer, uploaded, sheet_name=selected_sheet)
                if ok:
                    st.session_state.imports['cash_register'] = {'done': True, 'result': result}
                    st.success("✅ Cash Register data imported!")
                    if result and result.get('errors', 0) > 0:
                        st.warning(f"⚠️ {result['errors']} rows had issues and were skipped")
                    st.rerun()
                else:
                    st.error(f"❌ Import failed: {result}")


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
        if st.button("▶️ Go to Run Reconciliation", type="primary", key="nav_to_recon"):
            st.session_state['nav_radio'] = "Run Reconciliation"
            st.rerun()

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
        "Card/UPI payment terminal data for cross-validation.",
        'mswipe', MSwipeImporter, session_db, is_unlocked=sales_done,
        suffix=".csv"
    )

    # Step 5: Runner Notepad — dual mode
    render_notepad_step(session_db, is_unlocked=sales_done)

    # Step 6: Cash Register
    render_cash_register_step(session_db, is_unlocked=sales_done)


# ── Page: Run Reconciliation ──────────────────────────────

def page_reconciliation(session_db):
    st.header("⚙️ Reconciliation Engine")

    mode = st.radio("Mode", ["📅 Single Date", "📆 Date Range"], horizontal=True, key="recon_mode")

    if mode == "📅 Single Date":
        run_date = st.date_input("Select Date to Reconcile", value=date.today())

        if st.button("▶️ Start Reconciliation", type="primary"):
            with st.status(f"⚙️ Running Reconciliation for {run_date}...", expanded=True) as status:
                st.write("Running Matching Service...")
                matcher = MatchingService(session_db)
                match_stats = matcher.match_notepad_deliveries()
                mswipe_stats = matcher.match_mswipe_payments()

                st.write("Running Reconciliation rules...")
                recon = ReconciliationService(session_db)
                try:
                    run = recon.run_reconciliation(run_date)
                    status.update(label=f"Reconciliation Complete! Run ID: {run.id}", state="complete", expanded=False)
                    success = True
                except LaundryReconcilerError as e:
                    status.update(label=f"Reconciliation Failed: {e}", state="error", expanded=True)
                    success = False

            if success:
                col1, col2, col3 = st.columns(3)
                col1.metric("Notepad Matches",
                           f"{match_stats.get('exact', 0) + match_stats.get('fuzzy', 0)}")
                col2.metric("MSWIPE Matches", str(mswipe_stats.get('matched', 0)))
                col3.metric("Exceptions", str(run.summary_stats.get('total_exceptions', 0)))

                late = run.summary_stats.get('late_payment_exceptions', 0)
                if late > 0:
                    st.warning(f"⚠️ {late} late payment(s) detected")

                if st.button("📊 View Results", key="nav_to_results_single"):
                    st.session_state['nav_radio'] = "View Results"
                    st.rerun()

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
            # Run matching first
            with st.spinner("Running Matching Service..."):
                matcher = MatchingService(session_db)
                match_stats = matcher.match_notepad_deliveries()
                mswipe_stats = matcher.match_mswipe_payments()

            # Run range reconciliation with progress bar
            progress_bar = st.progress(0, text="Starting reconciliation...")
            status_text = st.empty()

            def on_progress(current, total):
                progress_bar.progress(current / total, text=f"Processing day {current}/{total}...")

            recon = ReconciliationService(session_db)
            totals = recon.run_reconciliation_range(start_date, end_date, progress_callback=on_progress)

            progress_bar.progress(1.0, text="✅ Complete!")

            # Show consolidated results
            st.success(f"✅ Range Reconciliation Complete!")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Days Processed", totals['days_processed'])
            col2.metric("Days with Activity", totals['days_with_activity'])
            col3.metric("Total Exceptions", totals['total_exceptions'])
            col4.metric("Days with Exceptions", totals['days_with_exceptions'])

            st.divider()

            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Order Exceptions", totals['order_exceptions'])
            col_b.metric("Late Payments", totals['late_payment_exceptions'])
            col_c.metric("Day Exceptions", totals['day_exceptions'])
            col_d.metric("Matching",
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


# ── Page: View Results ────────────────────────────────────

def page_results(session_db):
    st.header("📊 Reconciliation Dashboard")

    runs = session_db.query(ReconciliationRun).order_by(ReconciliationRun.run_date.desc()).all()
    if not runs:
        st.warning("No reconciliation runs found. Go to **Run Reconciliation** first.")
        return

    # View mode selector
    view_mode = st.radio("View Mode", ["📅 Single Run", "📆 Date Range"], horizontal=True, key="results_view_mode")

    if view_mode == "📅 Single Run":
        run_options = {f"{r.run_date} (ID: {r.id})": r.id for r in runs}
        selected_label = st.selectbox("Select Reconciliation Run", list(run_options.keys()))
        selected_id = run_options[selected_label]
        run = session_db.get(ReconciliationRun, selected_id)
        selected_runs = [run]
        run_ids = [selected_id]
        date_label = str(run.run_date)
    else:
        # Date range mode — use stored range or let user pick
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
        date_label = f"{start_dt} to {end_dt}"

        if not selected_runs:
            st.warning(f"No reconciliation runs found between {start_dt} and {end_dt}.")
            return

        st.info(f"📊 Showing results for **{len(selected_runs)} days** from {date_label}")

    st.divider()

    # ── Gather data for selected run(s) ──
    all_exceptions = session_db.query(OrderException).filter(
        OrderException.reconciliation_run_id.in_(run_ids)).all()

    # Deduplicate exceptions by (order_id, exception_type) — keep latest
    seen_ex = {}
    for e in all_exceptions:
        key = (e.order_id, e.exception_type)
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

    # ── Tabs ──
    tab_overview, tab_orders, tab_exceptions, tab_unmatched, tab_export = st.tabs([
        "📈 Overview", "📋 Reconciled Orders", "⚠️ Exceptions",
        "❓ Unmatched", "📥 Export"
    ])

    # ══════════════════════════════════════════════════════
    # TAB 1: Overview
    # ══════════════════════════════════════════════════════
    with tab_overview:
        # Top-level metrics
        total_ex = len(exceptions)
        high_ex = sum(1 for e in exceptions if e.severity == 'high')
        medium_ex = sum(1 for e in exceptions if e.severity == 'medium')
        low_ex = sum(1 for e in exceptions if e.severity in ('low', 'info'))
        late_ex = sum(
            (r.summary_stats or {}).get('late_payment_exceptions', 0) for r in selected_runs
        )

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("📅 Period", date_label)
        col2.metric("✅ Runs", str(len(selected_runs)))
        col3.metric("📋 Orders", str(len(recon_orders)))
        col4.metric("⚠️ Exceptions", str(total_ex))
        col5.metric("⏰ Late Payments", str(late_ex))

        st.divider()

        # Severity breakdown + exception type breakdown side by side
        col_sev, col_type = st.columns(2)

        with col_sev:
            st.subheader("Exceptions by Severity")
            if total_ex > 0:
                sev_data = pd.DataFrame({
                    'Severity': ['🔴 High', '🟡 Medium', '🟢 Low/Info'],
                    'Count': [high_ex, medium_ex, low_ex]
                })
                st.bar_chart(sev_data.set_index('Severity'), horizontal=True)
            else:
                st.success("No exceptions!")

        with col_type:
            st.subheader("Exceptions by Type")
            if total_ex > 0:
                type_counts = {}
                for e in exceptions:
                    type_counts[e.exception_type] = type_counts.get(e.exception_type, 0) + 1
                type_df = pd.DataFrame(
                    [{'Type': k, 'Count': v} for k, v in sorted(type_counts.items(), key=lambda x: -x[1])]
                )
                st.dataframe(type_df, width='stretch', hide_index=True)
            else:
                st.success("No exceptions!")

        st.divider()

        # Payment summary — dynamic, no hardcoded modes
        st.subheader("💰 Payment Summary")
        crm_payments_list = [p for p in day_payments if p.source == 'crm']
        mswipe_payments_list = [p for p in day_payments if p.source == 'mswipe']

        # Group CRM payments by mode
        crm_by_mode = {}
        for p in crm_payments_list:
            mode = p.payment_mode or 'Unknown'
            crm_by_mode[mode] = crm_by_mode.get(mode, 0) + float(p.amount)

        crm_total = sum(crm_by_mode.values())
        mswipe_total = sum(float(p.amount) for p in mswipe_payments_list)

        # GPay variants for variance calc (Google Pay, GPay, UPI)
        gpay_modes = {'Google Pay', 'GPay', 'UPI'}
        crm_gpay = sum(v for k, v in crm_by_mode.items() if k in gpay_modes)

        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("CRM Total", f"₹{crm_total:,.0f}")
        col_p2.metric("MSWIPE Total", f"₹{mswipe_total:,.0f}")
        col_p3.metric("GPay Variance", f"₹{crm_gpay - mswipe_total:,.0f}",
                      delta=f"₹{crm_gpay - mswipe_total:,.0f}",
                      delta_color="inverse" if crm_gpay != mswipe_total else "off")

        # Mode-wise breakdown table
        mode_icons = {'Cash': '�', 'Google Pay': '💳', 'GPay': '💳', 'UPI': '💳',
                      'Paytm': '�', 'Package': '📦', 'Card': '💳', 'Online': '🌐',
                      'Advance': '�', 'Due': '⏳'}
        pay_rows = []
        for mode in sorted(crm_by_mode.keys()):
            icon = mode_icons.get(mode, '🔹')
            pay_rows.append({
                'Mode': f"{icon} {mode}",
                'CRM Amount': f"₹{crm_by_mode[mode]:,.0f}",
                'Transactions': sum(1 for p in crm_payments_list if (p.payment_mode or 'Unknown') == mode)
            })
        if pay_rows:
            st.dataframe(pd.DataFrame(pay_rows), width='stretch', hide_index=True)

    # ══════════════════════════════════════════════════════
    # TAB 2: Reconciled Orders
    # ══════════════════════════════════════════════════════
    with tab_orders:
        st.subheader(f"Orders Active in {date_label}")
        if recon_orders:
            orders_data = []
            for o in recon_orders:
                # Only sum payments within the selected date range
                paid = sum(float(p.amount) for p in o.payments if p.id in in_range_payment_ids)
                excs = [e for e in exceptions if e.order_id == o.id]
                orders_data.append({
                    'Order #': o.order_number,
                    'Customer': o.customer_name or '—',
                    'Order Amount': f"₹{float(o.order_amount):,.0f}",
                    'Paid': f"₹{paid:,.0f}",
                    'Balance': f"₹{float(o.order_amount) - paid:,.0f}",
                    'Status': '⚠️ Exception' if excs else '✅ Clean',
                    'Issues': ', '.join(e.exception_type for e in excs) or '—'
                })
            st.dataframe(pd.DataFrame(orders_data), width='stretch', hide_index=True)

            # Summary row
            total_ordered = sum(float(o.order_amount) for o in recon_orders)
            total_paid = sum(
                sum(float(p.amount) for p in o.payments if p.id in in_range_payment_ids)
                for o in recon_orders
            )
            st.info(f"**Totals:** ₹{total_ordered:,.0f} ordered · ₹{total_paid:,.0f} paid · "
                    f"₹{total_ordered - total_paid:,.0f} outstanding · "
                    f"{sum(1 for d in orders_data if '✅' in d['Status'])}/{len(orders_data)} clean")
        else:
            st.info("No orders found for this date.")

    # ══════════════════════════════════════════════════════
    # TAB 3: Exceptions Queue
    # ══════════════════════════════════════════════════════
    with tab_exceptions:
        st.subheader("Exceptions Queue")

        if exceptions:
            # Filters
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            severities = sorted(set(e.severity for e in exceptions))
            filter_severity = col_f1.multiselect("Severity", severities, default=severities,
                                                 key="dash_filter_sev")
            types = sorted(set(e.exception_type for e in exceptions))
            filter_type = col_f2.multiselect("Type", types, default=types, key="dash_filter_type")
            statuses = sorted(set(e.resolution_status for e in exceptions))
            filter_status = col_f3.multiselect("Status", statuses, default=statuses,
                                               key="dash_filter_status")
            # Date filter (get dates from reconciliation runs linked to exceptions)
            ex_run_dates = sorted(set(
                r.run_date for r in selected_runs
                if r.id in {e.reconciliation_run_id for e in exceptions}
            ))
            if len(ex_run_dates) > 1:
                filter_dates = col_f4.multiselect("Date", [str(d) for d in ex_run_dates],
                                                  default=[str(d) for d in ex_run_dates],
                                                  key="dash_filter_date")
                filter_date_set = {d for d in ex_run_dates if str(d) in filter_dates}
                # Map run_id to run_date for filtering
                run_date_map = {r.id: r.run_date for r in selected_runs}
            else:
                filter_date_set = None
                run_date_map = {r.id: r.run_date for r in selected_runs}

            ex_data = []
            for ex in exceptions:
                if (ex.severity in filter_severity and
                    ex.exception_type in filter_type and
                    ex.resolution_status in filter_status):
                    # Date filter
                    if filter_date_set is not None:
                        ex_date = run_date_map.get(ex.reconciliation_run_id)
                        if ex_date not in filter_date_set:
                            continue

                    evidence_str = ''
                    if ex.evidence:
                        evidence_str = ', '.join(f"{k}: {v}" for k, v in ex.evidence.items()
                                                if k != 'raw_data')

                    # Get order details for drilldown
                    order_num = ex.order.order_number if ex.order else 'Day-Level'
                    customer = ex.order.customer_name if ex.order else '—'
                    amount = f"₹{float(ex.order.order_amount):,.0f}" if ex.order else '—'
                    ex_date = run_date_map.get(ex.reconciliation_run_id, '—')

                    ex_data.append({
                        'ID': ex.id,
                        'Date': str(ex_date),
                        'Order': order_num,
                        'Customer': customer,
                        'Amount': amount,
                        'Severity': '🔴' if ex.severity == 'high' else '🟡' if ex.severity == 'medium' else '🟢',
                        'Type': ex.exception_type,
                        'Evidence': evidence_str,
                        'Action': ex.suggested_action,
                        'Status': ex.resolution_status
                    })

            if ex_data:
                st.dataframe(pd.DataFrame(ex_data), width='stretch', hide_index=True)
                st.caption(f"Showing {len(ex_data)} of {len(exceptions)} exceptions")
            else:
                st.info("No exceptions match the selected filters.")

            # Resolution
            st.divider()
            st.subheader("Resolve Exception")
            ex_ids = [e['ID'] for e in ex_data] if ex_data else []
            if ex_ids:
                sel_id = st.selectbox("Select Exception ID", ex_ids, key="dash_resolve_id")
                sel_ex = next((e for e in ex_data if e['ID'] == sel_id), None)
                if sel_ex:
                    st.caption(f"**{sel_ex['Type']}** — {sel_ex['Order']} — {sel_ex['Evidence']}")
                resolution = st.radio("Action", ["resolved", "false_positive"], key="dash_resolve_act")
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
            st.success("🎉 No exceptions found for this run!")

    # ══════════════════════════════════════════════════════
    # TAB 4: Unmatched Entries
    # ══════════════════════════════════════════════════════
    with tab_unmatched:
        col_np, col_ms = st.columns(2)

        with col_np:
            st.subheader("📝 Unmatched Notepad")
            if unmatched_notepad:
                np_data = [{
                    'Date': d.delivery_date,
                    'Customer': d.customer_name or '—',
                    'Amount': f"₹{float(d.amount_collected or 0):,.0f}",
                    'Mode': d.payment_mode or '—',
                    'Runner': d.runner_name or '—'
                } for d in unmatched_notepad]
                st.dataframe(pd.DataFrame(np_data), width='stretch', hide_index=True)
                st.caption(f"{len(np_data)} unmatched entries")
            else:
                st.success("All notepad entries matched!")

        with col_ms:
            st.subheader("💳 Unmatched MSWIPE")
            if unmatched_mswipe:
                ms_data = [{
                    'Date': p.payment_date,
                    'Amount': f"₹{float(p.amount):,.0f}",
                    'Ref': str(p.mswipe_ref_ids) if p.mswipe_ref_ids else '—',
                    'Mode': p.original_mode or '—'
                } for p in unmatched_mswipe]
                st.dataframe(pd.DataFrame(ms_data), width='stretch', hide_index=True)
                st.caption(f"{len(ms_data)} unmatched entries")
            else:
                st.success("All MSWIPE entries matched!")

    # ══════════════════════════════════════════════════════
    # TAB 5: Export
    # ══════════════════════════════════════════════════════
    with tab_export:
        st.subheader("📥 Export to Excel")
        st.write("Generate a 6-sheet Excel workbook with all reconciliation data:")
        st.markdown("""
        1. **Reconciled Orders** — all orders with status
        2. **Exceptions** — flagged issues with evidence
        3. **Unmatched Notepad** — notepad entries without order matches
        4. **Unmatched MSWIPE** — MSWIPE payments without order matches
        5. **Daily Summary** — totals and variance calculations
        6. **Audit Log** — system activity log
        """)

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


# ── Main App ──────────────────────────────────────────────

st.set_page_config(
    page_title="Laundry Reconciler",
    page_icon="🧺",
    layout="wide"
)

load_css()

st.title("🧺 Laundry Reconciler")

# Sidebar navigation
st.sidebar.title("Navigation")
pages = ["Import Data", "Run Reconciliation", "View Results", "History"]
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
    elif page == "History":
        page_history(session_db)
finally:
    session_db.close()
