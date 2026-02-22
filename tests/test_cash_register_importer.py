import pytest
import os
import pandas as pd
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.db.base import Base
from src.importers.cash_register import CashRegisterImporter
from src.models.cash_register import CashRegisterEntry

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

def test_cash_register_normalize(session):
    importer = CashRegisterImporter(session)
    # Simulate data extracted from Excel
    raw_data = [
        {'entry_date': date(2023, 10, 25), 'closing_balance': 1000.0, 'raw_data': {}},
        {'entry_date': date(2023, 10, 26), 'closing_balance': 1500.0, 'raw_data': {}},
        # Skip 27th (holiday)
        {'entry_date': date(2023, 10, 28), 'closing_balance': 2200.0, 'raw_data': {}}
    ]

    normalized = importer.normalize(raw_data)

    # 25th: no prior in batch or DB -> derived = 1000 - 0 = 1000
    assert normalized[0]['entry_date'] == date(2023, 10, 25)
    assert normalized[0]['prior_closing_balance'] == 0.0
    assert normalized[0]['derived_cash_from_orders'] == 1000.0
    assert normalized[0]['validation_status'] == 'partial'

    # 26th: prior is 25th (1000) -> derived = 1500 - 1000 = 500
    assert normalized[1]['entry_date'] == date(2023, 10, 26)
    assert normalized[1]['prior_closing_balance'] == 1000.0
    assert normalized[1]['derived_cash_from_orders'] == 500.0
    assert normalized[1]['validation_status'] == 'valid'

    # 28th: prior is 26th (1500) via lookback -> derived = 2200 - 1500 = 700
    assert normalized[2]['entry_date'] == date(2023, 10, 28)
    assert normalized[2]['prior_closing_balance'] == 1500.0
    assert normalized[2]['derived_cash_from_orders'] == 700.0
    assert normalized[2]['validation_status'] == 'valid'

def test_cash_register_save(session):
    importer = CashRegisterImporter(session)
    data = [{
        'entry_date': date(2023, 10, 29),
        'closing_balance': 3000.0,
        'prior_closing_balance': 2200.0,
        'expenses_deposits': 0.0,
        'derived_cash_from_orders': 800.0,
        'validation_status': 'valid',
        'raw_data': {}
    }]

    importer.save(data)

    entry = session.query(CashRegisterEntry).filter_by(entry_date=date(2023, 10, 29)).first()
    assert entry is not None
    assert entry.closing_balance == 3000.0
    assert entry.derived_cash_from_orders == 800.0
