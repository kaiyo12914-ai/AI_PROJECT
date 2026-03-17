from .base import BaseRepository
from typing import List, Any, Optional

class DOCSRepository(BaseRepository):
    """
    Repository for handling document-related data (DOCS node).
    Example usage of the BaseRepository.
    """
    def __init__(self):
        # Default to sqlserver as per standard, or sybase if needed
        super().__init__(db_type="sqlserver")

    def get_document_by_id(self, doc_id: str) -> Any:
        sql = "SELECT * FROM DOCS_TABLE WHERE DOC_ID = ?"
        return self.query_one(sql, [doc_id])

    def list_recent_documents(self, limit: int = 10) -> List[Any]:
        sql = "SELECT * FROM DOCS_TABLE ORDER BY CREATED_AT DESC"
        return self.query_all(sql, limit=limit)

    def update_document_status(self, doc_id: str, status: str) -> int:
        sql = "UPDATE DOCS_TABLE SET STATUS = ? WHERE DOC_ID = ?"
        return self.execute(sql, [status, doc_id])
