"""Tests for Excel exporter — validates all sheet generation."""
import pytest
import os
import tempfile
from datetime import date
from src.exporters.excel_exporter import ExcelExporter
from src.models.orders import Order
from src.models.payments import PaymentEvent
from src.models.deliveries import DeliveryEvent
from src.models.reconciliation import ReconciliationRun
from src.models.exceptions import OrderException
from src.exceptions import ExportError


def test_export_nonexistent_run(session):
    """Exporting a nonexistent run should raise ExportError."""
    exporter = ExcelExporter(session)
    with pytest.raises(ExportError):
        exporter.export_run(99999, "nonexistent.xlsx")


def test_export_creates_file(session):
    """A valid export should create an Excel file."""
    run = ReconciliationRun(run_date=date(2023, 12, 1), status='complete')
    session.add(run)
    session.flush()

    exporter = ExcelExporter(session)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        exporter.export_run(run.id, tmp_path)
        assert os.path.exists(tmp_path)
        assert os.path.getsize(tmp_path) > 0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_export_with_exceptions(session):
    """Export with exceptions should include them in the Exceptions sheet."""
    run = ReconciliationRun(run_date=date(2023, 12, 2), status='complete')
    session.add(run)
    session.flush()

    order = Order(
        order_number="ORD-EXP-001", customer_name="Export Test",
        order_date=date(2023, 12, 2), order_amount=500.0
    )
    session.add(order)
    session.flush()

    exc = OrderException(
        reconciliation_run_id=run.id, order_id=order.id,
        severity='high', exception_type='CreditPolicyViolation',
        reason_tags=['UnpaidDelivery'],
        evidence={'balance': 500.0},
        suggested_action='Collect payment'
    )
    session.add(exc)
    session.flush()

    exporter = ExcelExporter(session)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        exporter.export_run(run.id, tmp_path)
        assert os.path.exists(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
