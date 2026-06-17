from __future__ import annotations

import unittest
from unittest.mock import patch

require_node_patcher = patch("webapps.portal.decorators.require_node", lambda *args, **kwargs: lambda f: f)
require_node_patcher.start()

from webapps.vanna.api import _mask_ct_employ_pii


class VannaPIIMaskingTestCase(unittest.TestCase):
    def test_no_ct_employ_table_not_masked(self):
        sql = "SELECT MPNO, NAME FROM SOME_OTHER_TABLE"
        columns = ["MPNO", "NAME"]
        rows = [("H123456789", "Alice"), ("H987654321", "Bob")]
        result = _mask_ct_employ_pii(sql, columns, rows)
        self.assertEqual(result, rows)

    def test_ct_employ_variations_masked(self):
        variations = [
            "SELECT MPNO, NAME FROM CT_EMPLOY",
            "SELECT MPNO, NAME FROM CT_EMPLOYE",
            "SELECT MPNO, NAME FROM CT_EMPLOYEE",
            "SELECT MPNO, NAME FROM ct_employee",
            "SELECT MPNO, NAME FROM CT_EMPLOYEE_SIMPLE",
        ]
        columns = ["MPNO", "NAME"]
        rows = [("H123456789", "Alice")]
        expected = [("H1234*****", "Alice")]

        for sql in variations:
            result = _mask_ct_employ_pii(sql, columns, rows)
            self.assertEqual(result, expected, f"Failed for SQL: {sql}")

    def test_multiple_pii_columns_masked(self):
        sql = "SELECT IDNO, EMPNO, MPNO, NAME FROM CT_EMPLOYE"
        columns = ["IDNO", "EMPNO", "MPNO", "NAME"]
        rows = [("A123456789", "E99999", "H111222333", "Alice")]
        expected = [("A1234*****", "E*****", "H1112*****", "Alice")]
        result = _mask_ct_employ_pii(sql, columns, rows)
        self.assertEqual(result, expected)

    def test_tuple_rows_remain_tuples(self):
        sql = "SELECT MPNO, NAME FROM CT_EMPLOYE"
        columns = ["MPNO", "NAME"]
        rows = [("H123456789", "Alice")]
        result = _mask_ct_employ_pii(sql, columns, rows)
        self.assertIsInstance(result[0], tuple)
        self.assertEqual(result, [("H1234*****", "Alice")])

    def test_list_rows_remain_lists(self):
        sql = "SELECT MPNO, NAME FROM CT_EMPLOYE"
        columns = ["MPNO", "NAME"]
        rows = [["H123456789", "Alice"]]
        result = _mask_ct_employ_pii(sql, columns, rows)
        self.assertIsInstance(result[0], list)
        self.assertEqual(result, [["H1234*****", "Alice"]])

    def test_dict_rows_masked_properly(self):
        sql = "SELECT MPNO, NAME FROM CT_EMPLOYE"
        columns = ["MPNO", "NAME"]
        rows = [{"MPNO": "H123456789", "NAME": "Alice"}]
        expected = [{"MPNO": "H1234*****", "NAME": "Alice"}]
        result = _mask_ct_employ_pii(sql, columns, rows)
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result, expected)

    def test_dict_rows_case_insensitive_keys(self):
        sql = "SELECT MPNO, NAME FROM CT_EMPLOYE"
        columns = ["MPNO", "NAME"]
        rows = [{"mpno": "H123456789", "name": "Alice"}]
        expected = [{"mpno": "H1234*****", "name": "Alice"}]
        result = _mask_ct_employ_pii(sql, columns, rows)
        self.assertIsInstance(result[0], dict)
        self.assertEqual(result, expected)

    def test_short_pii_value_fully_masked(self):
        sql = "SELECT MPNO FROM CT_EMPLOYE"
        columns = ["MPNO"]
        rows = [("123",)]
        expected = [("*****",)]
        result = _mask_ct_employ_pii(sql, columns, rows)
        self.assertEqual(result, expected)

    def test_none_value_ignored(self):
        sql = "SELECT MPNO FROM CT_EMPLOYE"
        columns = ["MPNO"]
        rows = [(None,)]
        expected = [(None,)]
        result = _mask_ct_employ_pii(sql, columns, rows)
        self.assertEqual(result, expected)
