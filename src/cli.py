import argparse
import sys
import os
import logging
from datetime import date
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
from src.exceptions import LaundryReconcilerError, FileValidationError
from dateutil.parser import parse

DB_PATH = "laundry_reconciler.db"

# Configure logging — suppress stack traces from user output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# Allowed file extensions per source type
ALLOWED_EXTENSIONS = {
    'crm': {'.csv', '.xlsx', '.xls'},
    'crm_delivery': {'.csv', '.xlsx', '.xls'},
    'crm_orders': {'.csv', '.xlsx', '.xls'},
    'mswipe': {'.csv', '.xlsx', '.xls'},
    'notepad': {'.csv', '.xlsx', '.xls'},
    'cash_register': {'.xlsx', '.xls'},
}

MAX_FILE_SIZE_MB = 50


def validate_file_path(file_path: str, source: str) -> str:
    """
    Validates the file path for security and correctness.

    Checks:
    - File exists
    - No path traversal
    - Allowed extension for the source type
    - File size within limits

    Returns:
        The resolved, absolute file path.

    Raises:
        FileValidationError: If validation fails.
    """
    # Resolve to absolute path and check for traversal
    abs_path = os.path.abspath(file_path)

    if not os.path.isfile(abs_path):
        raise FileValidationError(file_path, "File does not exist")

    # Check extension
    _, ext = os.path.splitext(abs_path)
    allowed = ALLOWED_EXTENSIONS.get(source, {'.csv', '.xlsx', '.xls'})
    if ext.lower() not in allowed:
        raise FileValidationError(
            file_path,
            f"Invalid file type '{ext}'. Allowed: {', '.join(sorted(allowed))}"
        )

    # Check file size
    size_mb = os.path.getsize(abs_path) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise FileValidationError(
            file_path,
            f"File too large ({size_mb:.1f} MB). Maximum: {MAX_FILE_SIZE_MB} MB"
        )

    return abs_path


def get_session():
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine)
    return Session()


def _run_with_session(func):
    """Decorator that provides a session and handles cleanup."""
    def wrapper(args):
        session = get_session()
        try:
            func(args, session)
        except LaundryReconcilerError as e:
            print(f"Error: {e}", file=sys.stderr)
            logger.debug("Details: %s", e.details, exc_info=True)
            sys.exit(1)
        except Exception as e:
            print(f"Unexpected error: {e}", file=sys.stderr)
            logger.debug("Unexpected error", exc_info=True)
            sys.exit(1)
        finally:
            session.close()
    return wrapper


def init_database(args):
    init_db(DB_PATH)
    print("Database initialized.")


@_run_with_session
def import_crm(args, session):
    path = validate_file_path(args.file, 'crm')
    importer = CRMImporter(session)
    result = importer.run(path)
    print(f"Imported CRM Sales data from {path}")
    print(f"  Orders: {result.get('imported', 'N/A')}, Errors: {result.get('errors', 0)}")


@_run_with_session
def import_crm_delivery(args, session):
    path = validate_file_path(args.file, 'crm_delivery')
    importer = CRMDeliveryImporter(session)
    result = importer.run(path)
    print(f"Imported CRM Delivery data from {path}")
    print(f"  Deliveries: {result.get('imported', 'N/A')}, Errors: {result.get('errors', 0)}")


@_run_with_session
def import_crm_orders(args, session):
    path = validate_file_path(args.file, 'crm_orders')
    importer = CRMOrdersImporter(session)
    result = importer.run(path)
    print(f"Imported CRM Orders data from {path}")
    print(f"  Orders: {result.get('imported', 'N/A')}, Errors: {result.get('errors', 0)}")


@_run_with_session
def import_mswipe(args, session):
    path = validate_file_path(args.file, 'mswipe')
    importer = MSwipeImporter(session)
    importer.run(path)
    print(f"Imported MSWIPE data from {path}")


@_run_with_session
def import_notepad(args, session):
    path = validate_file_path(args.file, 'notepad')
    importer = NotepadImporter(session)
    importer.run(path)
    print(f"Imported Notepad data from {path}")


@_run_with_session
def import_cash_register(args, session):
    path = validate_file_path(args.file, 'cash_register')
    importer = CashRegisterImporter(session)
    importer.run(path, year=args.year)
    print(f"Imported Cash Register data from {path}")


@_run_with_session
def run_reconciliation(args, session):
    try:
        run_date = parse(args.date).date()
    except ValueError:
        print(f"Invalid date format: {args.date}. Use YYYY-MM-DD.", file=sys.stderr)
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

    # Import CRM Sales
    p_crm = subparsers.add_parser('import-crm', help='Import CRM Sales & Delivery report')
    p_crm.add_argument('file', help='Path to CRM Sales Excel/CSV file')
    p_crm.set_defaults(func=import_crm)

    # Import CRM Delivery
    p_crm_del = subparsers.add_parser('import-crm-delivery', help='Import CRM Delivery report')
    p_crm_del.add_argument('file', help='Path to CRM Delivery Excel/CSV file')
    p_crm_del.set_defaults(func=import_crm_delivery)

    # Import CRM Orders
    p_crm_ord = subparsers.add_parser('import-crm-orders', help='Import CRM Orders report')
    p_crm_ord.add_argument('file', help='Path to CRM Orders Excel/CSV file')
    p_crm_ord.set_defaults(func=import_crm_orders)

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
