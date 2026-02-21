from sqlalchemy import Column, Integer, String, JSON, Boolean, DateTime, func
from src.db.base import Base

class ColumnMapping(Base):
    __tablename__ = 'column_mappings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    source_type = Column(String, nullable=False)  # crm, mswipe, cash_register
    mapping_config = Column(JSON, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

class ToleranceConfig(Base):
    __tablename__ = 'tolerance_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String, unique=True, nullable=False)
    config_value = Column(String, nullable=False)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
