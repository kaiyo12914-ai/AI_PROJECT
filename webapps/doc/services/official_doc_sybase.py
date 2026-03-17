from webapps.doc.services.docService import docService

def search_official_docs(keyword: str):
    """
    關鍵字搜尋公文
    """
    svc = docService()
    return svc.search_docs(keyword)
