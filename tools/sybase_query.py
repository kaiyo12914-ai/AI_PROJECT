# sybase_query.py - Minimal SYBASE SQL query tool with SQLAlchemy
import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, Tuple, List

from webapps.database.db_factory import db_query_all

SQL_1 = """
SELECT TOP 60
    EM.EM_GRSNO,
    EM.EM_PSID,
    CONVERT(VARBINARY(4000),COALESCE(EM.EM_SUBJ, TM.TM_SUBJ)) AS TD_SUBJ,
    CONVERT(VARCHAR(64), EF.EF_ID) AS EF_ID,
    CONVERT(VARBINARY(4000), EF.EF_NAME) AS EF_NAME,
    EF.EF_DATA,
    DATALENGTH(EF.EF_DATA) AS EF_DATA_LEN,
    EF.EF_PAGE
FROM mnda.dbo.DCS1_EMAL_TMP EM
LEFT JOIN mnda.dbo.DCS3_TRST_MST TM ON TM.TM_GRSNO = EM.EM_GRSNO
LEFT JOIN mnda.dbo.DCS1_EMAL_FILE EF ON EM.EM_FID = EF.EF_ID
WHERE 1=1
  AND TM.TM_PSID = ?
  AND EM.EM_GRSNO = ?
ORDER BY EF.EF_PAGE
"""

def connect_sybase(host: str = None, port: int = None,
                  dbname: str = None, user: str = None,
                  password: str = None) -> pyodbc.Connection:
    """Connect to SYBASE database"""
    conn_str = (
        f"DRIVER={{Sybase ASE}};"
        f"SERVER={host};"
        f"PORT={port};"
        f"DATABASE={dbname};"
        f"UID={user};"
        f"PWD={password};"
    )
    try:
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"Connection failed: {str(e)}")
        raise

def basic_sybase_query(query: str, params=None) -> None:
    """
    Execute a basic Sybase SQL query and print results.
    :param query: The SQL query to execute
    :param params: Parameters for parameterized queries (optional)
    """
    if not query or ';' in query or 'union' in query.lower() or 'select' not in query.lower():
        print("Error: Invalid query - only simple SELECT queries allowed")
        return

    try:
        # In a real environment, you would get these from your settings
        conn = connect_sybase(
            host="your-sybase-server",  # Replace with actual server name
            port=5000,                 # Default SYBASE port
            dbname="mnda",
            user="your_username",
            password="your_password"
        )

        print(f"\nExecuting query at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}:")
        print(f"  SQL: {query}")

        params = params or ()

        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]

        # Print header
        print(" | ".join(columns))
        print("-" * len(" | ".join(columns)))

        # Print results
        for row in rows:
            values = []
            for i, value in enumerate(row):
                if isinstance(value, (bytes, bytearray)):
                    # Convert binary data to base64 for display
                    values.append(base64.b64encode(value).decode('ascii')[:50] + '...')
                else:
                    values.append(str(value)[:50] + ('...' if len(str(value)) > 50 else ''))

            print(" | ".join(values))

        print(f"\nFound {len(rows)} rows")

    except Exception as e:
        print(f"Query failed: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    parser = argparse.ArgumentParser(description="Minimal SYBASE SQL query tool")
    parser.add_argument("--query", required=True, help="SQL SELECT query to execute")
    parser.add_argument("--param1", default=None, help="First parameter for the query")
    parser.add_argument("--param2", default=None, help="Second parameter for the query")
    args = parser.parse_args()

    params = []
    if args.param1:
        params.append(args.param1)
    if args.param2:
        params.append(args.param2)

    basic_sybase_query(args.query, tuple(params))

if __name__ == "__main__":
    raise SystemExit(main())