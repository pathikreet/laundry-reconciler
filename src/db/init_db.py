"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Database initialization script.
PRD Section: 5.1 Local data store (SQLite)
"""

import os
import re
from sqlalchemy import create_engine
from src.db.base import Base
from src.exceptions import DatabaseError

# Import all models to ensure they are registered with Base
# This is crucial for SQLAlchemy to detect and create all tables.
from src.db import *

# Allowed characters for database path: alphanumeric, underscore, hyphen, dot, slash, backslash
_SAFE_PATH_RE = re.compile(r'^[\w\-. /\\:]+$')


def init_db(db_path="laundry_reconciler.db"):
    """
    Initializes the SQLite database with the defined schema.

    Creates all tables if they do not exist.
    The default database file is 'laundry_reconciler.db' in the current directory.

    Args:
        db_path: Path to the SQLite database file. Must be a safe filesystem path.

    Raises:
        DatabaseError: If the database path is invalid or initialization fails.
    """
    # Sanitize database path to prevent injection
    if not _SAFE_PATH_RE.match(db_path):
        raise DatabaseError(
            f"Invalid database path: '{db_path}'. "
            f"Path must contain only alphanumeric characters, underscores, hyphens, dots, and separators.",
            details={"db_path": db_path}
        )

    # Ensure the path doesn't contain traversal sequences
    normalized = os.path.normpath(db_path)
    if '..' in normalized.split(os.sep):
        raise DatabaseError(
            f"Invalid database path: '{db_path}'. Path traversal is not allowed.",
            details={"db_path": db_path}
        )

    try:
        engine = create_engine(f"sqlite:///{normalized}")
        Base.metadata.create_all(engine)
        print(f"Database initialized at {normalized}")
    except Exception as e:
        raise DatabaseError(
            f"Failed to initialize database at '{normalized}': {e}",
            details={"db_path": normalized, "error": str(e)}
        )


if __name__ == "__main__":
    init_db()
