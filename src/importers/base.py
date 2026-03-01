from abc import ABC, abstractmethod
from typing import List, Dict, Any
from sqlalchemy.orm import Session

class BaseImporter(ABC):
    """
    Abstract base class for all data importers.
    """
    def __init__(self, db_session: Session):
        self.db = db_session

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
        """
        pass

    @abstractmethod
    def save(self, data: List[Dict[str, Any]]) -> None:
        """
        Saves the validated data to the database.
        """
        pass

    def run(self, file_path: str, **kwargs) -> int:
        """
        Executes the full import pipeline: import -> normalize -> validate -> save.
        Returns the number of validated records processed.
        """
        raw_data = self.import_data(file_path, **kwargs)
        normalized_data = self.normalize(raw_data)
        validated_data = self.validate(normalized_data)
        self.save(validated_data)
        return len(validated_data)
