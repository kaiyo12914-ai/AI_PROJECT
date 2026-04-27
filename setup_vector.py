import psycopg2

try:
    conn = psycopg2.connect('postgresql://postgres:Ntou6228@192.168.0.137:5432/projectnotes')
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    print("Vector extension successfully created in projectnotes DB!")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Failed to create vector extension: {e}")
