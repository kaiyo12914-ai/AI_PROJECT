import psycopg2
conn = psycopg2.connect('postgresql://dating_user:Ntou6228@192.168.0.137:5432/dating')
cur = conn.cursor()

# Get all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = [row[0] for row in cur.fetchall()]

print('Tables in public schema:')
for t in tables:
    try:
        cur.execute(f'SELECT count(*) FROM "{t}"')
        count = cur.fetchone()[0]
        print(f' - {t} (Rows: {count})')
    except Exception as e:
        print(f' - {t}: Error: {e}')
        conn.rollback()

# Check installed extensions
print('\nInstalled Extensions:')
cur.execute("SELECT extname FROM pg_extension;")
extensions = [row[0] for row in cur.fetchall()]
for ext in extensions:
    print(f' - {ext}')

cur.close()
conn.close()
