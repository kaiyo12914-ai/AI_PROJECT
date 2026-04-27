import psycopg2
conn = psycopg2.connect('postgresql://projectnotes_user:Ntou6228@192.168.0.137:5432/projectnotes')
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
tables = [row[0] for row in cur.fetchall()]
print(f"Total tables: {len(tables)}")
print(f"Includes projectnotes_document_chunk: {'projectnotes_document_chunk' in tables}")
print(f"Includes django_migrations: {'django_migrations' in tables}")
cur.close()
conn.close()
