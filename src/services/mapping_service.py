"""
Task: IMP-005 - Column Mapping Engine with Profile Persistence
Description: Service for managing column mappings.
PRD Section: 2.1 Inputs (Mapping UI)
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from src.repositories.config import MappingRepository
from src.models.config import ColumnMapping

class MappingService:
    """
    Core service for managing column mapping profiles.

    This service allows users to:
    - Auto-detect best-match columns based on common patterns.
    - Save and load mapping profiles for different import sources.
    - Validate that required columns are mapped.

    Attributes:
        repository: MappingRepository for data access.
    """

    def __init__(self, session: Session):
        self.repository = MappingRepository(session)
        self.session = session

    def get_mapping(self, source_type: str, profile_name: Optional[str] = None) -> Optional[Dict[str, str]]:
        """
        Retrieves the mapping configuration for a given source type.

        If profile_name is provided, it attempts to load that specific profile.
        Otherwise, it falls back to the default profile for the source type.

        Args:
            source_type: 'crm', 'mswipe', or 'cash_register'.
            profile_name: Optional name of a saved profile.

        Returns:
            Dictionary mapping source columns to internal fields.
        """
        if profile_name:
            mapping = self.repository.get_by_name(profile_name)
            if mapping and mapping.source_type == source_type:
                return mapping.mapping_config

        # Fallback to default
        mapping = self.repository.get_default(source_type)
        return mapping.mapping_config if mapping else None

    def save_mapping(self, name: str, source_type: str, mapping_config: Dict[str, str], is_default: bool = False):
        """
        Persists a new or updated mapping profile.

        Args:
            name: Unique name for the profile.
            source_type: 'crm', 'mswipe', etc.
            mapping_config: The column mapping dictionary.
            is_default: Whether to set this as the default for the source type.
        """
        existing = self.repository.get_by_name(name)
        if existing:
            existing.mapping_config = mapping_config
            existing.is_default = is_default
            self.repository.update(existing)
        else:
            new_mapping = ColumnMapping(
                name=name,
                source_type=source_type,
                mapping_config=mapping_config,
                is_default=is_default
            )
            self.repository.create(new_mapping)

    def auto_detect_mapping(self, available_columns: List[str], required_fields: List[str]) -> Dict[str, str]:
        """
        Attempts to automatically map available columns to required fields.

        This uses heuristic matching (fuzzy logic could be added here) based on
        common naming conventions.

        Args:
            available_columns: List of columns found in the input file.
            required_fields: List of internal field names needed.

        Returns:
            Dictionary of suggested mappings.
        """
        mapping = {}
        column_map_lower = {col.lower(): col for col in available_columns}

        # Heuristics for common fields
        heuristics = {
            "order_number": ["order number", "order no", "ref no", "id"],
            "order_date": ["order date", "date", "created at"],
            "customer_name": ["customer name", "customer", "name"],
            "order_amount": ["order amount", "amount", "total", "value", "price", "total amount"],
            "amount": ["amount", "total", "value", "price", "txn amount"],
            "payment_mode": ["payment mode", "mode", "method"],
            "status": ["status", "state"]
        }

        for field in required_fields:
            # Check exact match first
            if field in available_columns:
                mapping[field] = field
                continue

            # Check heuristics
            possible_names = heuristics.get(field, [])
            for name in possible_names:
                if name in column_map_lower:
                    mapping[field] = column_map_lower[name]
                    break

        return mapping
