from sqlalchemy import create_engine

# import pymysql
from google.cloud.sql import connector
from src.utils.config import (
    INSTANCE_CONNECTION_NAME,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DB_NAME,
)


class MySQLClient:
    """
    Thin wrapper around the Cloud SQL Python Connector (MySQL) and a SQLAlchemy
    engine built with `creator`. This class centralizes connection handling and
    exposes a reusable engine for the application.

    Args:
        instance_uri (str): Cloud SQL instance connection name (project:region:instance).
        user (str): MySQL username.
        password (str): MySQL password.
        database (str): Target database name.
        refresh_strategy (str, optional): Placeholder for future connector refresh
            strategies; not used with the current connector. Defaults to "background".

    Attributes:
        instance_uri (str): Stored instance connection name.
        user (str): Stored DB username.
        password (str): Stored DB password.
        database (str): Stored DB name.
        mysql_engine (sqlalchemy.engine.Engine): Precreated SQLAlchemy engine.
    """

    def __init__(
        self,
        instance_uri: str,
        user: str,
        password: str,
        database: str,
        refresh_strategy: str = "background",
    ):
        self.instance_uri = instance_uri
        self.user = user
        self.password = password
        self.database = database
        # self.connector = Connector(refresh_strategy=refresh_strategy)
        self.mysql_engine = self.get_engine()

    # Initialize Cloud SQL Python Connector
    def get_connection(self):
        """
        Produces a live MySQL DB-API connection via the Cloud SQL connector.

        Returns:
            Any: A PyMySQL DB-API connection object usable by SQLAlchemy's `creator`.
        """
        # connector = Connector(ip_type=IPTypes.PUBLIC)  # Or IPTypes.PRIVATE if configured
        connect = connector.Connector()
        conn = connect.connect(
            INSTANCE_CONNECTION_NAME,
            "pymysql",
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DB_NAME,
        )
        return conn

    def get_engine(self):
        """
        Builds a SQLAlchemy engine that uses the connector's `creator` callback
        to open MySQL connections.

        Returns:
            sqlalchemy.engine.Engine: Engine bound to Cloud SQL (MySQL) via PyMySQL.
        """
        engine = create_engine(
            "mysql+pymysql://",
            creator=self.get_connection,
        )
        return engine


# Create a process-wide client instance for reuse.
mysql_client = MySQLClient(
    INSTANCE_CONNECTION_NAME, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB_NAME
)


def get_engine():
    """
    Provides the application-wide SQLAlchemy engine configured for Cloud SQL (MySQL).

    Returns:
        sqlalchemy.engine.Engine: Engine retrieved from the shared MySQLClient.
    """
    return mysql_client.engine
