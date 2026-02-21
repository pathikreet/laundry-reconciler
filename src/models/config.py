"""
Task: DATA-001 - Database Schema Design & SQLite Setup
Description: Configuration entities for column mappings and tolerances.
PRD Section: 2.1 Inputs (Mapping UI), 3.2 Tolerances
"""

from sqlalchemy import Column, Integer, String, JSON, Boolean, DateTime, func
from src.db.base import Base

class ColumnMapping(Base):
    """
    Stores user-defined mappings between source columns and application fields.

    This allows the system to handle varying column names in CRM/MSWIPE exports.
    It supports multiple profiles per source type.

    Attributes:
        name: A unique name for the mapping profile (e.g., 'CRM Default').
        source_type: The type of import ('crm', 'mswipe', 'cash_register').
        mapping_config: JSON dictionary mapping source columns to internal fields.
        is_default: Whether this profile is automatically selected.
    """
    __tablename__ = 'column_mappings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    source_type = Column(String, nullable=False)  # crm, mswipe, cash_register
    mapping_config = Column(JSON, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

class ToleranceConfig(Base):
    """
    Stores key-value pairs for system-wide configuration and tolerances.

    This allows runtime adjustment of matching thresholds without code changes.
    Values are stored as strings and cast by the application.

    Attributes:
        config_key: The setting name (e.g., 'amount_match_tolerance_inr').
        config_value: The setting value (e.g., '2.0').
        description: User-friendly description of what this setting controls.
    """
    __tablename__ = 'tolerance_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String, unique=True, nullable=False)
    config_value = Column(String, nullable=False)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
