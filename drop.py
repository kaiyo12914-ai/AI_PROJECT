import psycopg2
conn = psycopg2.connect('postgresql://projectnotes_user:mpcdbadm@mpcai.mpc.mil.tw:5432/projectnotes')
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'projectnotes_%'")
tables = [r[0] for r in cur.fetchall()]
for t in tables:
    print(f"Dropping {t}")
    cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE;')
print('Dropped remaining tables:', tables)
cur.close()
conn.close()
