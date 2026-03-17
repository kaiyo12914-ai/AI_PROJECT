from webapps.repositories.DOCS import DOCSRepository
from typing import List, Any, Optional

class DOCSService:
    """
    Service layer for document-related business logic.
    Coordinates with the DOCSRepository.
    """
    def __init__(self):
        self.repository = DOCSRepository()

    def get_document(self, doc_id: str) -> Any:
        # Wrap repository call with business logic if needed
        doc = self.repository.get_document_by_id(doc_id)
        if not doc:
            # Handle not found case (e.g., logging or raising custom exception)
            return None
        return doc

    def get_recent_docs(self, limit: int = 5) -> List[Any]:
        return self.repository.list_recent_documents(limit=limit)

    def process_document(self, doc_id: str, action: str) -> bool:
        """Example business logic: updating status based on action."""
        status_map = {
            "approve": "APPROVED",
            "reject": "REJECTED",
            "review": "PENDING"
        }
        new_status = status_map.get(action.lower())
        if not new_status:
            return False
            
        rows_affected = self.repository.update_document_status(doc_id, new_status)
        return rows_affected > 0
