import psycopg2
try:
    conn = psycopg2.connect('postgresql://projectnotes_user:Ntou6228@192.168.0.137:5432/projectnotes')
    cur = conn.cursor()
    cur.execute('SELECT version();')
    version = cur.fetchone()[0]
    print(f"PostgreSQL Version Information:\n{version}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Failed to get PG version: {e}")
