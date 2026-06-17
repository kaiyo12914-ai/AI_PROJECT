from __future__ import annotations

import re
import sqlparse
from sqlparse.sql import TokenList, Token
from sqlparse.tokens import DML, DDL, Keyword

# 嚴格禁止的關鍵字 (DML/DDL 等寫入、控制或修改操作)
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE",
    "DROP", "ALTER", "CREATE", "TRUNCATE",
    "EXEC", "EXECUTE", "CALL", "BEGIN",
    "GRANT", "REVOKE", "REPLACE"
}


def _check_token_list(token_list: TokenList) -> tuple[bool, str]:
    for token in token_list.tokens:
        if token.is_group:
            # 遞迴檢查子節點 (如子查詢、巢狀運算式)
            safe, err = _check_token_list(token)
            if not safe:
                return False, err
        else:
            # 檢查當前 token 類型與值
            val = str(token.value).strip().upper()
            
            # 若屬於 DML/DDL 或 Keyword 且名列禁止清單，判定為不安全
            if token.ttype in (DML, DDL) or (token.ttype == Keyword and val in FORBIDDEN_KEYWORDS):
                if val in FORBIDDEN_KEYWORDS:
                    return False, f"SQL contains forbidden operation: '{val}'"
    return True, ""


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    使用 sqlparse 分析 SQL 的語法樹 (AST)，確認是否僅含有安全的 DQL 語句 (SELECT/WITH SELECT)。
    """
    clean_sql = (sql or "").strip()
    if not clean_sql:
        return False, "SQL statement is empty"
        
    try:
        parsed = sqlparse.parse(clean_sql)
    except Exception as exc:
        return False, f"SQL parsing error: {exc}"
        
    if not parsed:
        return False, "Failed to parse SQL statement"
        
    # 檢查是否有複數個 SQL 語句被以分號串接 (防止 Semicolon injection)
    if len(parsed) > 1:
        # 如果最後一個陳述句只是空白或分號，則可接受，否則禁止
        non_empty = [p for p in parsed if p.value.strip() and p.value.strip() != ";"]
        if len(non_empty) > 1:
            return False, "Multiple SQL statements are not allowed"

    stmt = parsed[0]
    
    # 尋找第一個非空非註解的 token，確保以 SELECT 或 WITH 開頭
    first_keyword = None
    for token in stmt.tokens:
        if token.is_whitespace:
            continue
        if isinstance(token, sqlparse.sql.Comment) or str(token.value).startswith("--") or str(token.value).startswith("/*"):
            continue
        first_keyword = str(token.value).strip().upper()
        break

    if not first_keyword:
        return False, "Failed to identify the starting keyword of the SQL statement"

    if first_keyword not in ("SELECT", "WITH"):
        return False, f"Invalid SQL statement start: '{first_keyword}'. Only SELECT or WITH SELECT are allowed."

    # 檢查最上層的 statement type，必須是 SELECT 或 WITH
    stmt_type = stmt.get_type()
    if stmt_type not in ("SELECT", "UNKNOWN"):
        # 由於 WITH ... SELECT 在 sqlparse 中可能被判定為 UNKNOWN，
        # 所以只有當它被判定為非 SELECT 且亦非 UNKNOWN 時才直接報錯。
        return False, f"Invalid SQL statement type: '{stmt_type}'. Only SELECT or WITH SELECT are allowed."

    # 對整個 AST 語法樹進行深度遍歷與遞迴檢查
    safe, err = _check_token_list(stmt)
    if not safe:
        return False, err

    # 再次做一個保險的安全字串驗證（不分大小寫），確保無遺漏的 DML/DDL 敏感字眼出現在關鍵的執行詞彙中
    # 避免利用 sqlparse 的一些解析邊界漏洞
    sql_upper = clean_sql.upper()
    
    for kw in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", sql_upper):
            return False, f"Security check: detected forbidden keyword '{kw}' (word-boundary)"

    return True, ""
