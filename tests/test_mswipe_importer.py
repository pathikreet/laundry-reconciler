import pytest
import os
import pandas as pd
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.importers.mswipe import MSwipeImporter
from src.models.payments import PaymentEvent

@pytest.fixture(scope="module")
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine

@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

def test_mswipe_importer_normalize(session):
    importer = MSwipeImporter(session)
    raw_data = [{
        'Status': 'Successful',
        'Amount': '150.50',
        'PaymentDate': '2023-10-26',
        'CardType': 'Visa',
        'RR_NO': '123456'
    }, {
        'Status': 'Failed',
        'Amount': '200.00',
        'PaymentDate': '2023-10-26',
        'CardType': 'MasterCard',
        'RR_NO': '789012'
    }]

    normalized = importer.normalize(raw_data)
    # Only successful transaction should be normalized
    assert len(normalized) == 1
    row = normalized[0]
    assert row['payment_date'] == date(2023, 10, 26)
    assert row['amount'] == 150.50
    assert row['payment_mode'] == 'Visa'
    assert row['ref_id'] == '123456'

def test_mswipe_importer_save(session):
    importer = MSwipeImporter(session)
    data = [{
        'payment_date': date(2023, 10, 27),
        'amount': 300.0,
        'payment_mode': 'UPI',
        'original_mode': 'UPI',
        'ref_id': 'REF001',
        'raw_data': {}
    }]

    importer.save(data)

    payment = session.query(PaymentEvent).filter_by(source='mswipe').first()
    assert payment is not None
    assert payment.amount == 300.0
    assert payment.payment_mode == 'GPay' # Should be normalized to GPay
    assert payment.mswipe_ref_ids == ['REF001']

def test_mswipe_importer_duplicate(session):
    importer = MSwipeImporter(session)
    data = [{
        'payment_date': date(2023, 10, 27),
        'amount': 300.0,
        'payment_mode': 'UPI',
        'original_mode': 'UPI',
        'ref_id': 'REF001',
        'raw_data': {}
    }]

    # Save twice
    importer.save(data)
    importer.save(data)

    payments = session.query(PaymentEvent).filter_by(source='mswipe').all()
    assert len(payments) == 1


# ══════════════════════════════════════════════════════════
# Date Parsing Tests — ISO date bug regression suite
# ══════════════════════════════════════════════════════════
# These tests guard against the bug where pandas converts a date like
# "12-Jan-2026" into the ISO string "2026-01-12 00:00:00", and then
# dateutil.parse with dayfirst=True misinterprets it as "2026-12-01"
# (December 1st instead of January 12th).

class TestMSwipeDateParsing:
    """Tests for MSwipeImporter._parse_date across all expected formats."""

    @pytest.fixture(autouse=True)
    def setup(self, session):
        self.importer = MSwipeImporter(session)

    # ── Slash-separated dates (MM/DD/YYYY) — XLSX format ──

    def test_slash_date_unambiguous(self):
        """04/30/2026 — only valid as April 30 (30 can't be a month)."""
        assert self.importer._parse_date("04/30/2026 17:29:00") == date(2026, 4, 30)

    def test_slash_date_ambiguous(self):
        """04/01/2026 — US format means April 1, NOT Jan 4."""
        assert self.importer._parse_date("04/01/2026 12:00:00") == date(2026, 4, 1)

    def test_slash_date_no_time(self):
        """04/15/2026 — without time component."""
        assert self.importer._parse_date("04/15/2026") == date(2026, 4, 15)

    # ── Dash-separated dates (DD-Mon-YYYY) — CSV format ──

    def test_dash_day_mon_year(self):
        """27-Feb-2026 — standard CSV format."""
        assert self.importer._parse_date("27-Feb-2026") == date(2026, 2, 27)

    def test_dash_day_mon_year_ambiguous_day(self):
        """12-Jan-2026 — the bug date: must NOT become Dec 1."""
        result = self.importer._parse_date("12-Jan-2026")
        assert result == date(2026, 1, 12), f"Expected Jan 12, got {result}"

    # ── ISO format strings (YYYY-MM-DD) — from pandas str() ──

    def test_iso_string_jan12(self):
        """'2026-01-12 00:00:00' — ISO string that must stay Jan 12, NOT Dec 1."""
        result = self.importer._parse_date("2026-01-12 00:00:00")
        assert result == date(2026, 1, 12), f"ISO date bug: expected Jan 12, got {result}"

    def test_iso_string_dec1(self):
        """'2026-12-01' — explicit Dec 1 must remain Dec 1."""
        assert self.importer._parse_date("2026-12-01") == date(2026, 12, 1)

    def test_iso_string_no_time(self):
        """'2026-03-15' — ISO without time."""
        assert self.importer._parse_date("2026-03-15") == date(2026, 3, 15)

    # ── Edge cases ──

    def test_none_returns_none(self):
        assert self.importer._parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert self.importer._parse_date("") is None

    def test_nan_returns_none(self):
        assert self.importer._parse_date(float('nan')) is None


class TestMSwipeXlsxPortalDateParsing:
    """Tests for _parse_date when _is_xlsx_portal=True (XLSX transactions report).

    The XLSX portal exports dates as MM/DD/YYYY. When both components are <= 12,
    Excel auto-converts them to YYYY-DD-MM (swapping month and day). The importer
    must swap them back.
    """

    @pytest.fixture(autouse=True)
    def setup(self, session):
        self.importer = MSwipeImporter(session)
        self.importer._is_xlsx_portal = True

    def test_iso_swap_april_11(self):
        """'2026-11-04' in XLSX portal = originally 04/11 = April 11."""
        result = self.importer._parse_date("2026-11-04 17:53:20")
        assert result == date(2026, 4, 11), f"Expected Apr 11, got {result}"

    def test_iso_swap_april_1(self):
        """'2026-01-04' in XLSX portal = originally 04/01 = April 1."""
        result = self.importer._parse_date("2026-01-04 12:00:00")
        assert result == date(2026, 4, 1), f"Expected Apr 1, got {result}"

    def test_iso_swap_march_4(self):
        """'2026-04-03' in XLSX portal = originally 03/04 = March 4."""
        result = self.importer._parse_date("2026-04-03 10:00:00")
        assert result == date(2026, 3, 4), f"Expected Mar 4, got {result}"

    def test_slash_unaffected(self):
        """Slash dates are already MM/DD/YYYY — no swap needed."""
        result = self.importer._parse_date("04/30/2026 17:29:00")
        assert result == date(2026, 4, 30)

    def test_iso_unambiguous_day_gt_12(self):
        """'2026-30-04' — day=30 > 12, swap fails gracefully → date(2026,4,30)."""
        result = self.importer._parse_date("2026-30-04 12:00:00")
        assert result == date(2026, 4, 30), f"Expected Apr 30, got {result}"



class TestExpensesDateParsing:
    """Tests for ExpensesImporter._parse_date — same ISO bug regression."""

    @pytest.fixture(autouse=True)
    def setup(self, session):
        from src.importers.expenses import ExpensesImporter
        self.importer = ExpensesImporter(session)

    def test_iso_string_jan12(self):
        """'2026-01-12 00:00:00' must be Jan 12, NOT Dec 1."""
        result = self.importer._parse_date("2026-01-12 00:00:00")
        assert result == date(2026, 1, 12), f"ISO date bug: expected Jan 12, got {result}"

    def test_iso_string_dec1(self):
        """'2026-12-01' must stay Dec 1."""
        assert self.importer._parse_date("2026-12-01") == date(2026, 12, 1)

    def test_dd_mm_yyyy_slash(self):
        """'12/01/2026' — DD/MM/YYYY with dayfirst=True → Jan 12."""
        result = self.importer._parse_date("12/01/2026")
        assert result == date(2026, 1, 12), f"Expected Jan 12, got {result}"

    def test_dd_mm_yyyy_dash(self):
        """'12-01-2026' — DD-MM-YYYY with dayfirst=True → Jan 12."""
        result = self.importer._parse_date("12-01-2026")
        assert result == date(2026, 1, 12), f"Expected Jan 12, got {result}"

    def test_excel_serial_number(self):
        """Excel serial 44573 → some valid date (should not crash)."""
        result = self.importer._parse_date(44573)
        assert result is not None

    def test_none_returns_none(self):
        assert self.importer._parse_date(None) is None
