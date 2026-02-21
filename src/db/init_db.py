"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Database initialization script.
PRD Section: 5.1 Local data store (SQLite)
"""

from sqlalchemy import create_engine
from src.db.base import Base
import os

# Import all models to ensure they are registered with Base
# This is crucial for SQLAlchemy to detect and create all tables.
from src.db import *

def init_db(db_path="laundry_reconciler.db"):
    """
    Initializes the SQLite database with the defined schema.

    Creates all tables if they do not exist.
    The default database file is 'laundry_reconciler.db' in the current directory.

    Args:
        db_path: Path to the SQLite database file.
    """
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    print(f"Database initialized at {db_path}")

if __name__ == "__main__":
    init_db()
