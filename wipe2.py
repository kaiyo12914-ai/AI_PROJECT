import psycopg2
conn = psycopg2.connect('postgresql://postgres:Ntou6228@192.168.0.137:5432/projectnotes')
conn.autocommit = True
cur = conn.cursor()
cur.execute("DROP SCHEMA public CASCADE;")
cur.execute("CREATE SCHEMA public;")
cur.execute("GRANT ALL ON SCHEMA public TO public;")
cur.execute("GRANT ALL ON SCHEMA public TO projectnotes_user;")
cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
print("Tables after wipe:", cur.fetchone()[0])
cur.close()
conn.close()
