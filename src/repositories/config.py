"""
Task: DATA-002 - Data Access Layer (ConfigRepository, MappingRepository)
Description: Data access for configuration and column mappings.
PRD Section: 2.1 Inputs (Mapping UI), 3.2 Tolerances
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.config import ColumnMapping, ToleranceConfig
from src.db.base import Base

class ConfigRepository(BaseRepository[ToleranceConfig]):
    """
    Handles retrieval and persistence of system-wide settings.

    This repository manages user-configurable tolerances (PRD 3.2).
    It allows the application to adapt to changing business rules.

    Attributes:
        session: SQLAlchemy session object.
    """

    def __init__(self, session: Session):
        """Initializes the repository for the ToleranceConfig model."""
        super().__init__(session, ToleranceConfig)

    def get_value(self, key: str) -> Optional[str]:
        """
        Retrieves a configuration value by its unique key.

        This is used throughout the application to fetch tolerance settings.

        Args:
            key: The unique string identifier (e.g., 'amount_match_tolerance_inr').
        """
        config = self.session.query(ToleranceConfig).filter(ToleranceConfig.config_key == key).first()
        return config.config_value if config else None

    def set_value(self, key: str, value: str):
        """
        Updates or creates a configuration setting.

        This allows users to modify tolerances via the UI.

        Args:
            key: The unique string identifier.
            value: The new configuration value.
        """
        config = self.session.query(ToleranceConfig).filter(ToleranceConfig.config_key == key).first()
        if config:
            config.config_value = value
        else:
            config = ToleranceConfig(config_key=key, config_value=value)
            self.session.add(config)
        self.session.commit()

class MappingRepository(BaseRepository[ColumnMapping]):
    """
    Handles storage and retrieval of column mapping profiles.

    This repository supports the Import Wizard by saving user preferences
    for mapping import file columns to internal fields (IMP-005).

    Attributes:
        session: SQLAlchemy session object.
    """

    def __init__(self, session: Session):
        """Initializes the repository for the ColumnMapping model."""
        super().__init__(session, ColumnMapping)

    def get_by_name(self, name: str) -> Optional[ColumnMapping]:
        """
        Retrieves a mapping profile by its unique name.

        This allows users to load specific saved configurations.

        Args:
            name: The user-defined profile name.
        """
        return self.session.query(ColumnMapping).filter(ColumnMapping.name == name).first()

    def get_default(self, source_type: str) -> Optional[ColumnMapping]:
        """
        Retrieves the default mapping profile for a given source type.

        This automatically applies saved settings for CRM, MSWIPE, etc.

        Args:
            source_type: 'crm', 'mswipe', or 'cash_register'.
        """
        return self.session.query(ColumnMapping).filter(ColumnMapping.source_type == source_type, ColumnMapping.is_default == True).first()
