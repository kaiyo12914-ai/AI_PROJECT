from __future__ import annotations

import unittest
from webapps.vanna.sql_guard import validate_sql


class VannaSQLGuardTestCase(unittest.TestCase):
    def test_safe_queries_pass(self):
        # 簡單 SELECT 語句
        safe_sql1 = "SELECT * FROM public.official_docs WHERE id = 1"
        is_safe, err = validate_sql(safe_sql1)
        self.assertTrue(is_safe, f"Expected safe but got error: {err}")

        # 包含 JOIN 且帶有換行
        safe_sql2 = """
            SELECT t.id, t.name, d.content 
            FROM my_table t 
            JOIN doc_table d ON t.id = d.t_id
            WHERE t.status = 'ACTIVE'
        """
        is_safe, err = validate_sql(safe_sql2)
        self.assertTrue(is_safe)

        # WITH ... SELECT 語句
        safe_sql3 = """
            WITH latest_docs AS (
                SELECT * FROM documents ORDER BY created_at DESC LIMIT 10
            )
            SELECT id, title FROM latest_docs WHERE enabled = true
        """
        is_safe, err = validate_sql(safe_sql3)
        self.assertTrue(is_safe)

    def test_dml_queries_blocked(self):
        # INSERT
        is_safe, err = validate_sql("INSERT INTO users (name) VALUES ('Hacker')")
        self.assertFalse(is_safe)
        self.assertTrue("forbidden" in err.lower() or "only select" in err.lower())

        # UPDATE
        is_safe, err = validate_sql("UPDATE config SET val = 'evil' WHERE key = 'proxy'")
        self.assertFalse(is_safe)

        # DELETE
        is_safe, err = validate_sql("DELETE FROM session WHERE expired = true")
        self.assertFalse(is_safe)

        # MERGE
        is_safe, err = validate_sql("MERGE INTO target USING source ON (id = key) WHEN MATCHED THEN UPDATE SET a = b")
        self.assertFalse(is_safe)

    def test_ddl_queries_blocked(self):
        # DROP
        is_safe, err = validate_sql("DROP TABLE important_logs")
        self.assertFalse(is_safe)

        # ALTER
        is_safe, err = validate_sql("ALTER TABLE users ADD COLUMN is_admin boolean")
        self.assertFalse(is_safe)

        # CREATE
        is_safe, err = validate_sql("CREATE TABLE backdoor (id serial, pw text)")
        self.assertFalse(is_safe)

        # TRUNCATE
        is_safe, err = validate_sql("TRUNCATE TABLE audits")
        self.assertFalse(is_safe)

    def test_control_statements_blocked(self):
        # EXEC
        is_safe, err = validate_sql("EXEC sp_msforeachtable 'DROP TABLE ?'")
        self.assertFalse(is_safe)

        # CALL
        is_safe, err = validate_sql("CALL execute_arbitrary_code()")
        self.assertFalse(is_safe)

        # GRANT/REVOKE
        is_safe, err = validate_sql("GRANT ALL PRIVILEGES ON DATABASE postgres TO hacker")
        self.assertFalse(is_safe)

    def test_semicolon_injection_blocked(self):
        # 雙重陳述句注入
        is_safe, err = validate_sql("SELECT * FROM users; DROP TABLE audits;")
        self.assertFalse(is_safe)
        self.assertIn("multiple sql statements", err.lower())

    def test_comment_bypass_blocked(self):
        # 使用註解繞過 AST 解析
        is_safe, err = validate_sql("SELECT * FROM users; -- DROP TABLE users")
        self.assertFalse(is_safe)
        self.assertIn("forbidden keyword 'DROP'", err)

    def test_incomplete_sql_blocked(self):
        # 殘缺、非 SELECT/WITH 開頭的 SQL 片段
        is_safe, err = validate_sql("MITEM = G.MITEM AND MLLREV = G.MLLREV")
        self.assertFalse(is_safe)
        self.assertIn("only select or with select are allowed", err.lower())

        # 僅有註解但無 query
        is_safe, err = validate_sql("-- Just a comment")
        self.assertFalse(is_safe)
        self.assertIn("failed to identify", err.lower())
