import argparse
import sys
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
from dateutil.parser import parse

DB_PATH = "laundry_reconciler.db"

def get_session():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine)
    return Session()

def init_database(args):
    init_db(DB_PATH)
    print("Database initialized.")

def import_crm(args):
    session = get_session()
    importer = CRMImporter(session)
    importer.run(args.file)
    print(f"Imported CRM data from {args.file}")

def import_mswipe(args):
    session = get_session()
    importer = MSwipeImporter(session)
    importer.run(args.file)
    print(f"Imported MSWIPE data from {args.file}")

def import_notepad(args):
    session = get_session()
    importer = NotepadImporter(session)
    importer.run(args.file)
    print(f"Imported Notepad data from {args.file}")

def import_cash_register(args):
    session = get_session()
    importer = CashRegisterImporter(session)
    importer.run(args.file, year=args.year)
    print(f"Imported Cash Register data from {args.file}")

def run_reconciliation(args):
    session = get_session()
    try:
        run_date = parse(args.date).date()
    except ValueError:
        print(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
        return

    # Matching
    print("Running Matching Service...")
    matcher = MatchingService(session)
    matcher.match_notepad_deliveries()
    matcher.match_mswipe_payments()

    # Reconciliation
    print(f"Running Reconciliation for {run_date}...")
    recon = ReconciliationService(session)
    run = recon.run_reconciliation(run_date)

    print(f"Reconciliation complete. Run ID: {run.id}, Status: {run.status}")

    if args.export:
        exporter = ExcelExporter(session)
        output = f"reconciliation_report_{run_date}.xlsx"
        exporter.export_run(run.id, output)
        print(f"Report exported to {output}")

def main():
    parser = argparse.ArgumentParser(description="Laundry Reconciler CLI")
    subparsers = parser.add_subparsers()

    # Init DB
    p_init = subparsers.add_parser('init-db', help='Initialize database')
    p_init.set_defaults(func=init_database)

    # Import CRM
    p_crm = subparsers.add_parser('import-crm', help='Import CRM data')
    p_crm.add_argument('file', help='Path to CRM Excel/CSV file')
    p_crm.set_defaults(func=import_crm)

    # Import MSWIPE
    p_ms = subparsers.add_parser('import-mswipe', help='Import MSWIPE data')
    p_ms.add_argument('file', help='Path to MSWIPE CSV file')
    p_ms.set_defaults(func=import_mswipe)

    # Import Notepad
    p_np = subparsers.add_parser('import-notepad', help='Import Notepad data')
    p_np.add_argument('file', help='Path to Notepad Excel/CSV file')
    p_np.set_defaults(func=import_notepad)

    # Import Cash Register
    p_cr = subparsers.add_parser('import-cash', help='Import Cash Register data')
    p_cr.add_argument('file', help='Path to Cash Register Excel file')
    p_cr.add_argument('--year', type=int, default=date.today().year, help='Year of the cash register sheet')
    p_cr.set_defaults(func=import_cash_register)

    # Run Reconciliation
    p_run = subparsers.add_parser('reconcile', help='Run reconciliation for a date')
    p_run.add_argument('date', help='Date to reconcile (YYYY-MM-DD)')
    p_run.add_argument('--export', action='store_true', help='Export results to Excel')
    p_run.set_defaults(func=run_reconciliation)

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
