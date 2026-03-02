"""Error-path and edge-case tests for importers and services."""
import pytest
from datetime import date
from src.importers.crm import CRMImporter
from src.importers.mswipe import MSwipeImporter
from src.importers.notepad import NotepadImporter
from src.services.matching import MatchingService
from src.services.reconciliation import ReconciliationService
from src.models.orders import Order
from src.models.deliveries import DeliveryEvent
from src.exceptions import LaundryReconcilerError


def test_crm_normalize_empty(session):
    """Normalizing empty data should return empty list."""
    importer = CRMImporter(session)
    result = importer.normalize([])
    assert result == []


def test_crm_normalize_missing_amount(session):
    """Missing amount fields should default to 0."""
    importer = CRMImporter(session)
    raw = [{
        'Order Number': 'ORD-ERR-001',
        'Customer Name': 'Test',
        'Order Date': '2023-10-26',
    }]
    result = importer.normalize(raw)
    assert len(result) == 1
    assert result[0]['payment_received'] == 0.0
    assert result[0]['adjustments'] == 0.0
    assert result[0]['balance'] == 0.0


def test_mswipe_normalize_filters_failed(session):
    """MSWIPE normalize should filter out non-successful transactions."""
    importer = MSwipeImporter(session)
    raw = [
        {'Status': 'Failed', 'Amount': '100', 'PaymentDate': '2023-10-26', 'RR_NO': '1'},
        {'Status': 'Cancelled', 'Amount': '200', 'PaymentDate': '2023-10-26', 'RR_NO': '2'},
    ]
    result = importer.normalize(raw)
    assert len(result) == 0


def test_matching_no_deliveries(session):
    """Matching should succeed gracefully when there are no unmatched deliveries."""
    service = MatchingService(session)
    stats = service.match_notepad_deliveries()
    assert stats['total'] >= 0  # Should not crash


def test_matching_no_mswipe(session):
    """Matching should succeed gracefully when there are no unmatched MSWIPE payments."""
    service = MatchingService(session)
    stats = service.match_mswipe_payments()
    assert stats['total'] >= 0


def test_reconciliation_no_data(session):
    """Reconciliation should complete without exceptions for dates with no data."""
    service = ReconciliationService(session)
    run = service.run_reconciliation(run_date=date(2099, 1, 1))
    assert run.status == 'complete'
    assert run.summary_stats['total_exceptions'] == 0


def test_notepad_normalize_missing_fields(session):
    """Notepad normalize should handle rows with missing optional fields."""
    importer = NotepadImporter(session)
    raw = [{
        'Date': '2023-10-26',
        'Amount': '100',
    }]
    result = importer.normalize(raw)
    assert len(result) == 1
    assert result[0]['delivery_date'] == date(2023, 10, 26)
    assert result[0]['amount_collected'] == 100.0


def test_fuzzy_match_no_candidates(session):
    """Fuzzy matching with no candidates should return None."""
    service = MatchingService(session)
    order, score, evidence = service._find_fuzzy_order(
        name="NonexistentPerson",
        amount=12345.0,
        event_date=date(2099, 12, 31)
    )
    assert order is None
    assert score == 0.0
