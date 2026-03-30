import logging
import os
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from src.exceptions import ImportError as AppImportError

logger = logging.getLogger(__name__)


def read_excel_auto(file_path: str, **kwargs) -> pd.DataFrame:
    """Read an Excel file, auto-detecting the engine based on extension.
    
    .xls files require engine='xlrd', .xlsx files use 'openpyxl' (default).
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.xls':
        kwargs.setdefault('engine', 'xlrd')
    return pd.read_excel(file_path, **kwargs)


def sanitize_raw_data(data: dict) -> dict:
    """Convert non-JSON-serializable values (datetime, date, Timestamp) to strings.
    
    Excel files often contain datetime objects in cells which cause
    'Object of type datetime is not JSON serializable' when stored in JSON columns.
    """
    import datetime as dt
    clean = {}
    for k, v in data.items():
        if isinstance(v, (dt.datetime, dt.date, pd.Timestamp)):
            clean[k] = str(v)
        elif isinstance(v, float) and pd.isna(v):
            clean[k] = None
        else:
            clean[k] = v
    return clean


class BaseImporter(ABC):
    """
    Abstract base class for all data importers.

    Provides a transactional import pipeline: import → normalize → validate → save.
    If any step fails, the entire import is rolled back to maintain data consistency.
    """
    def __init__(self, db_session: Session):
        self.db = db_session
        self.errors: List[Dict[str, Any]] = []

    @abstractmethod
    def import_data(self, file_path: str, **kwargs) -> List[Dict[str, Any]]:
        """
        Parses the input file and returns a list of raw data dictionaries.
        """
        pass

    @abstractmethod
    def normalize(self, raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalizes the raw data into a standard format.
        """
        pass

    @abstractmethod
    def validate(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validates the data against business rules.
        Returns only valid rows; invalid rows are collected in self.errors.
        """
        pass

    @abstractmethod
    def save(self, data: List[Dict[str, Any]]) -> None:
        """
        Saves the validated data to the database.
        """
        pass

    def run(self, file_path: str, **kwargs) -> Dict[str, Any]:
        """
        Executes the full import pipeline with transaction management.

        If save fails, the transaction is rolled back to prevent partial imports.
        Valid rows are processed even if some rows fail validation (graceful degradation).

        Returns:
            A summary dict with counts: total, imported, errors.
        """
        self.errors = []

        try:
            raw_data = self.import_data(file_path, **kwargs)
            normalized_data = self.normalize(raw_data)
            validated_data = self.validate(normalized_data)

            if validated_data:
                self.save(validated_data)
                self.db.commit()
            else:
                logger.warning("No valid data to import from %s", file_path)

        except AppImportError:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            logger.error("Import failed for %s: %s", file_path, str(e))
            raise AppImportError(
                f"Import failed for '{file_path}': {e}",
                details={"file_path": file_path, "error": str(e)}
            )

        summary = {
            "total": len(raw_data) if 'raw_data' in dir() else 0,
            "imported": len(validated_data) if 'validated_data' in dir() else 0,
            "errors": len(self.errors),
            "error_details": self.errors[:10]  # Limit to first 10 errors
        }

        if self.errors:
            logger.warning(
                "Import of %s completed with %d errors out of %d rows",
                file_path, len(self.errors), summary["total"]
            )

        return summary
