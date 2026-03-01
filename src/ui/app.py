import streamlit as st
import pandas as pd
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.db.init_db import init_db
from src.importers.crm import CRMImporter
from src.importers.mswipe import MSwipeImporter
from src.importers.cash_register import CashRegisterImporter
from src.importers.notepad import NotepadImporter
from src.services.matching import MatchingService
from src.services.reconciliation import ReconciliationService
from src.exporters.excel_exporter import ExcelExporter
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException

DB_PATH = "laundry_reconciler.db"

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

def get_session():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine)
    return Session()

st.set_page_config(page_title="Laundry Reconciler", layout="wide")

st.title("Laundry Reconciler MVP")

# Sidebar
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Import Data", "Run Reconciliation", "View Results", "History"])

session = get_session()

if page == "Import Data":
    st.header("Import Wizard")

    st.subheader("1. CRM Data")
    crm_file = st.file_uploader(
        "Upload CRM Excel/CSV",
        type=['csv', 'xlsx'],
        help="Upload the daily sales export from your CRM system."
    )
    if crm_file:
        with st.expander("Preview CRM Data", expanded=False):
            preview_uploaded_file(crm_file)

        if st.button("Import CRM"):
            # Save temp file
            with open("temp_crm.xlsx", "wb") as f:
                f.write(crm_file.getbuffer())

            importer = CRMImporter(session)
            try:
                importer.run("temp_crm.xlsx")
                st.success("CRM Data Imported Successfully!")
            except Exception as e:
                st.error(f"Error importing CRM: {e}")

    st.subheader("2. MSWIPE Data")
    ms_file = st.file_uploader(
        "Upload MSWIPE CSV",
        type=['csv', 'xlsx'],
        help="Upload the daily payments export from MSWIPE."
    )
    if ms_file:
        with st.expander("Preview MSWIPE Data", expanded=False):
            preview_uploaded_file(ms_file)

        if st.button("Import MSWIPE"):
            with open("temp_ms.csv", "wb") as f:
                f.write(ms_file.getbuffer())

            importer = MSwipeImporter(session)
            try:
                importer.run("temp_ms.csv")
                st.success("MSWIPE Data Imported Successfully!")
            except Exception as e:
                st.error(f"Error importing MSWIPE: {e}")

    st.subheader("3. Notepad Data")
    np_file = st.file_uploader(
        "Upload Notepad Excel/CSV",
        type=['csv', 'xlsx'],
        help="Upload the runner notepad entries for deliveries."
    )
    if np_file:
        with st.expander("Preview Notepad Data", expanded=False):
            preview_uploaded_file(np_file)

        if st.button("Import Notepad"):
            with open("temp_np.xlsx", "wb") as f:
                f.write(np_file.getbuffer())

            importer = NotepadImporter(session)
            try:
                importer.run("temp_np.xlsx")
                st.success("Notepad Data Imported Successfully!")
            except Exception as e:
                st.error(f"Error importing Notepad: {e}")

    st.subheader("4. Cash Register Data")
    cr_file = st.file_uploader(
        "Upload Cash Register Excel",
        type=['xlsx'],
        help="Upload the yearly cash register workbook."
    )
    year = st.number_input("Year", min_value=2000, max_value=2100, value=date.today().year)
    if cr_file:
        with st.expander("Preview Cash Register Data", expanded=False):
            preview_uploaded_file(cr_file)

        if st.button("Import Cash Register"):
            with open("temp_cr.xlsx", "wb") as f:
                f.write(cr_file.getbuffer())

            importer = CashRegisterImporter(session)
            try:
                importer.run("temp_cr.xlsx", year=year)
                st.success("Cash Register Data Imported Successfully!")
            except Exception as e:
                st.error(f"Error importing Cash Register: {e}")

elif page == "Run Reconciliation":
    st.header("Reconciliation Engine")

    run_date = st.date_input("Select Date to Reconcile", value=date.today())

    if st.button("Start Reconciliation"):
        with st.status("Running Reconciliation Process...", expanded=True) as status:
            st.write("Running Matching Service...")
            matcher = MatchingService(session)
            matcher.match_notepad_deliveries()
            matcher.match_mswipe_payments()
            st.write("Matching Service Complete.")

            st.write(f"Running Reconciliation for {run_date}...")
            recon = ReconciliationService(session)
            try:
                run = recon.run_reconciliation(run_date)
                status.update(label="Reconciliation Complete!", state="complete", expanded=False)
                st.success(f"Reconciliation Complete! Run ID: {run.id}, Status: {run.status}")
            except Exception as e:
                status.update(label="Reconciliation Failed", state="error")
                st.error(f"Reconciliation Failed: {e}")

elif page == "View Results":
    st.header("Reconciliation Results")

    # Select Run
    runs = session.query(ReconciliationRun).order_by(ReconciliationRun.run_date.desc()).all()
    if not runs:
        st.warning("No runs found.")
    else:
        run_options = {f"{r.run_date} (ID: {r.id})": r.id for r in runs}
        selected_run_label = st.selectbox("Select Run", list(run_options.keys()))
        selected_run_id = run_options[selected_run_label]

        run = session.get(ReconciliationRun, selected_run_id)

        # Summary Stats
        st.subheader("Daily Summary")
        col1, col2 = st.columns(2)
        col1.metric("Run Date", str(run.run_date))
        col2.metric("Status", run.status)

        # Exceptions
        st.subheader("Exceptions Queue")
        exceptions = session.query(OrderException).filter_by(reconciliation_run_id=selected_run_id).all()

        if exceptions:
            ex_data = []
            for ex in exceptions:
                ex_data.append({
                    'Order ID': ex.order.order_number if ex.order else 'N/A',
                    'Severity': ex.severity,
                    'Type': ex.exception_type,
                    'Reason': ex.reason_tags,
                    'Action': ex.suggested_action,
                    'Status': ex.resolution_status
                })
            st.dataframe(pd.DataFrame(ex_data))
        else:
            st.success("No exceptions found for this run!")

        # Export
        if st.button("Generate Excel Report"):
            exporter = ExcelExporter(session)
            output_file = f"report_{run.run_date}.xlsx"
            exporter.export_run(selected_run_id, output_file)

            with open(output_file, "rb") as f:
                st.download_button(
                    label="Download Excel Report",
                    data=f,
                    file_name=output_file,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

elif page == "History":
    st.header("Audit History")
    st.write("Coming soon...")

session.close()
