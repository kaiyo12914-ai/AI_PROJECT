from __future__ import annotations
from webapps.repositories.base import BaseRepository

class docRepository(BaseRepository):
    """
    DOC 子系統數據倉儲 (Repository)
    封裝對 Sybase 與內部各表的實際查詢與執行操作。
    """
    
    def query_all(
        self,
        sql: str,
        params: list | dict | None = None,
        db_type: str = "sybase",
        db_profile: str = "",
    ):
        """
        封裝 BaseRepository.query_all，預設走 sybase
        """
        return super().query_all(sql, params, db_type=db_type, profile=db_profile)

    def query_one(
        self,
        sql: str,
        params: list | dict | None = None,
        db_type: str = "sybase",
        db_profile: str = "",
    ):
        """
        封裝 BaseRepository.query_one，預設走 sybase
        """
        return super().query_one(sql, params, db_type=db_type, profile=db_profile)

    def execute(
        self,
        sql: str,
        params: list | dict | None = None,
        db_type: str = "sybase",
        db_profile: str = "",
    ):
        """
        封裝 BaseRepository.execute，預設走 sybase
        """
        return super().execute(sql, params, db_type=db_type, profile=db_profile)
