"""
Task: IMP-000 - Import Pipeline Base
Description: Abstract base class for all file importers.
PRD Section: 2. Inputs & normalization
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import pandas as pd
from sqlalchemy.orm import Session
from src.models.reconciliation import ReconciliationRun
from src.models.audit import AuditLog

class BaseImporter(ABC):
    """
    Abstract base class defining the interface for all data importers.

    This ensures a consistent API for importing CRM, MSWIPE, and other data sources.
    It handles common tasks like logging and error reporting.

    Attributes:
        session: SQLAlchemy session for database operations.
        run_id: The ID of the current ReconciliationRun.
    """

    def __init__(self, session: Session, run_id: Optional[int] = None):
        self.session = session
        self.run_id = run_id

    @abstractmethod
    def parse_file(self, file_path: str, column_mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Parses the input file and returns a list of normalized records.

        Args:
            file_path: Path to the input file (Excel/CSV).
            column_mapping: Dictionary mapping source columns to internal fields.

        Returns:
            List of dictionaries representing the parsed data rows.

        Raises:
            ValueError: If the file format is invalid or required columns are missing.
        """
        pass

    @abstractmethod
    def persist_data(self, data: List[Dict[str, Any]]) -> int:
        """
        Saves the parsed data to the database.

        Args:
            data: List of normalized records from parse_file().

        Returns:
            Number of records successfully inserted.
        """
        pass

    def log_import(self, source_type: str, file_name: str, count: int, status: str = "success"):
        """
        Logs the import action to the AuditLog.

        Args:
            source_type: 'crm', 'mswipe', etc.
            file_name: Name of the imported file.
            count: Number of records imported.
            status: Outcome of the import.
        """
        if self.run_id:
            audit = AuditLog(
                reconciliation_run_id=self.run_id,
                action_type="import",
                entity_type=source_type,
                entity_id=None,
                new_value={"file": file_name, "count": count, "status": status},
                performed_by="system"
            )
            self.session.add(audit)
            self.session.commit()
