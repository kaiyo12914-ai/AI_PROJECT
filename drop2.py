import psycopg2
conn = psycopg2.connect('postgresql://projectnotes_user:mpcdbadm@mpcai.mpc.mil.tw:5432/projectnotes')
conn.autocommit = True
cur = conn.cursor()

# Drop public schema and recreate it
cur.execute("DROP SCHEMA public CASCADE;")
cur.execute("CREATE SCHEMA public;")
cur.execute("GRANT ALL ON SCHEMA public TO public;")
cur.execute("GRANT ALL ON SCHEMA public TO projectnotes_user;")

print('Recreated public schema, all tables dropped.')
cur.close()
conn.close()
