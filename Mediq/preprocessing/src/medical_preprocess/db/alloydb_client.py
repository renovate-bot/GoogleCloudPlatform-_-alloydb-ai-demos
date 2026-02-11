from __future__ import annotations
import sqlalchemy
from sqlalchemy.engine import Engine
from google.cloud.alloydbconnector import Connector
from ..config import AlloyDBConfig

class AlloyDBClient:
    """Create SQLAlchemy engines backed by the AlloyDB connector."""

    def __init__(self, config: AlloyDBConfig, refresh_strategy: str = "background") -> None:
        self._config = config
        self._connector = Connector(refresh_strategy=refresh_strategy)

    def _creator(self):
        return self._connector.connect(
            self._config.instance_uri,
            "pg8000",
            user=self._config.user,
            password=self._config.password,
            db=self._config.database,
        )

    def create_engine(self) -> Engine:
        engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=self._creator)
        engine.dialect.description_encoding = None
        return engine

    def close(self) -> None:
        self._connector.close()
