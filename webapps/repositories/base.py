from typing import Any, List, Optional
from webapps.database.db_factory import db_query_one, db_query_all, db_execute, DBType, Params

class BaseRepository:
    """
    Base Repository class that provides common database operations.
    All database interactions must use db_factory methods.
    """
    def __init__(self, db_type: DBType = "sqlserver"):
        self.db_type = db_type

    def query_one(
        self,
        sql: str,
        params: Params = None,
        db_type: DBType = None,
        profile: str = "",
    ) -> Any:
        """Execute a query and return a single row."""
        target_db = db_type or self.db_type
        return db_query_one(target_db, sql, params, profile=profile)

    def query_all(
        self,
        sql: str,
        params: Params = None,
        limit: int = 0,
        db_type: DBType = None,
        profile: str = "",
    ) -> List[Any]:
        """Execute a query and return all matching rows."""
        target_db = db_type or self.db_type
        return db_query_all(target_db, sql, params, limit=limit, profile=profile)

    def execute(
        self,
        sql: str,
        params: Params = None,
        db_type: DBType = None,
        profile: str = "",
    ) -> int:
        """Execute a non-query SQL statement (INSERT, UPDATE, DELETE)."""
        target_db = db_type or self.db_type
        return db_execute(target_db, sql, params, profile=profile)
