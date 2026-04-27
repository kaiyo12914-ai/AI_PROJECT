import psycopg2
conn = psycopg2.connect('postgresql://projectnotes_user:Ntou6228@192.168.0.137:5432/projectnotes')
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'projectnotes_%'")
tables = [row[0] for row in cur.fetchall()]
print(f"Projectnotes tables: {tables}")
cur.close()
conn.close()
