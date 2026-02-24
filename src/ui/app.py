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
        with st.expander("Preview Data", expanded=False):
            try:
                if crm_file.name.endswith('.csv'):
                    df_preview = pd.read_csv(crm_file)
                else:
                    df_preview = pd.read_excel(crm_file)
                st.dataframe(df_preview.head())
                crm_file.seek(0)
            except Exception as e:
                st.error(f"Error reading preview: {e}")

        if st.button("Import CRM", type="primary"):
            with st.status("Importing CRM Data...", expanded=True) as status:
                # Save temp file
                with open("temp_crm.xlsx", "wb") as f:
                    f.write(crm_file.getbuffer())

                status.write("Processing file...")
                importer = CRMImporter(session)
                try:
                    count = importer.run("temp_crm.xlsx")
                    status.update(label=f"CRM Data Imported Successfully! ({count} records)", state="complete", expanded=False)
                    st.success(f"CRM Data Imported Successfully! ({count} records)")
                except Exception as e:
                    status.update(label="Import Failed", state="error")
                    st.error(f"Error importing CRM: {e}")

    st.subheader("2. MSWIPE Data")
    ms_file = st.file_uploader(
        "Upload MSWIPE CSV",
        type=['csv', 'xlsx'],
        help="Upload the daily payments export from MSWIPE."
    )
    if ms_file:
        with st.expander("Preview Data", expanded=False):
            try:
                if ms_file.name.endswith('.csv'):
                    df_preview = pd.read_csv(ms_file)
                else:
                    df_preview = pd.read_excel(ms_file)
                st.dataframe(df_preview.head())
                ms_file.seek(0)
            except Exception as e:
                st.error(f"Error reading preview: {e}")

        if st.button("Import MSWIPE", type="primary"):
            with st.status("Importing MSWIPE Data...", expanded=True) as status:
                with open("temp_ms.csv", "wb") as f:
                    f.write(ms_file.getbuffer())

                status.write("Processing file...")
                importer = MSwipeImporter(session)
                try:
                    count = importer.run("temp_ms.csv")
                    status.update(label=f"MSWIPE Data Imported Successfully! ({count} records)", state="complete", expanded=False)
                    st.success(f"MSWIPE Data Imported Successfully! ({count} records)")
                except Exception as e:
                    status.update(label="Import Failed", state="error")
                    st.error(f"Error importing MSWIPE: {e}")

    st.subheader("3. Notepad Data")
    np_file = st.file_uploader(
        "Upload Notepad Excel/CSV",
        type=['csv', 'xlsx'],
        help="Upload the runner notepad entries for deliveries."
    )
    if np_file:
        with st.expander("Preview Data", expanded=False):
            try:
                if np_file.name.endswith('.csv'):
                    df_preview = pd.read_csv(np_file)
                else:
                    df_preview = pd.read_excel(np_file)
                st.dataframe(df_preview.head())
                np_file.seek(0)
            except Exception as e:
                st.error(f"Error reading preview: {e}")

        if st.button("Import Notepad", type="primary"):
            with st.status("Importing Notepad Data...", expanded=True) as status:
                with open("temp_np.xlsx", "wb") as f:
                    f.write(np_file.getbuffer())

                status.write("Processing file...")
                importer = NotepadImporter(session)
                try:
                    count = importer.run("temp_np.xlsx")
                    status.update(label=f"Notepad Data Imported Successfully! ({count} records)", state="complete", expanded=False)
                    st.success(f"Notepad Data Imported Successfully! ({count} records)")
                except Exception as e:
                    status.update(label="Import Failed", state="error")
                    st.error(f"Error importing Notepad: {e}")

    st.subheader("4. Cash Register Data")
    cr_file = st.file_uploader(
        "Upload Cash Register Excel",
        type=['xlsx'],
        help="Upload the yearly cash register workbook."
    )
    year = st.number_input("Year", min_value=2000, max_value=2100, value=date.today().year)
    if cr_file:
        with st.expander("Preview Data", expanded=False):
            try:
                df_preview = pd.read_excel(cr_file)
                st.dataframe(df_preview.head())
                cr_file.seek(0)
            except Exception as e:
                st.error(f"Error reading preview: {e}")

        if st.button("Import Cash Register", type="primary"):
            with st.status("Importing Cash Register Data...", expanded=True) as status:
                with open("temp_cr.xlsx", "wb") as f:
                    f.write(cr_file.getbuffer())

                status.write("Processing file...")
                importer = CashRegisterImporter(session)
                try:
                    count = importer.run("temp_cr.xlsx", year=year)
                    status.update(label=f"Cash Register Data Imported Successfully! ({count} records)", state="complete", expanded=False)
                    st.success(f"Cash Register Data Imported Successfully! ({count} records)")
                except Exception as e:
                    status.update(label="Import Failed", state="error")
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
