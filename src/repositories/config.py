from typing import List, Optional
from sqlalchemy.orm import Session
from src.repositories.base import BaseRepository
from src.models.config import ColumnMapping, ToleranceConfig
from src.db.base import Base

class ConfigRepository(BaseRepository[ToleranceConfig]):
    def __init__(self, session: Session):
        super().__init__(session, ToleranceConfig)

    def get_value(self, key: str) -> Optional[str]:
        config = self.session.query(ToleranceConfig).filter(ToleranceConfig.config_key == key).first()
        return config.config_value if config else None

    def set_value(self, key: str, value: str):
        config = self.session.query(ToleranceConfig).filter(ToleranceConfig.config_key == key).first()
        if config:
            config.config_value = value
        else:
            config = ToleranceConfig(config_key=key, config_value=value)
            self.session.add(config)
        self.session.commit()

class MappingRepository(BaseRepository[ColumnMapping]):
    def __init__(self, session: Session):
        super().__init__(session, ColumnMapping)

    def get_by_name(self, name: str) -> Optional[ColumnMapping]:
        return self.session.query(ColumnMapping).filter(ColumnMapping.name == name).first()

    def get_default(self, source_type: str) -> Optional[ColumnMapping]:
        return self.session.query(ColumnMapping).filter(ColumnMapping.source_type == source_type, ColumnMapping.is_default == True).first()
