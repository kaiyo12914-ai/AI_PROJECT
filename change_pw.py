import psycopg2

try:
    # Connect as postgres superuser
    conn = psycopg2.connect('postgresql://postgres:Ntou6228@192.168.0.137:5432/postgres')
    conn.autocommit = True
    cur = conn.cursor()
    
    # Change the password for projectnotes_user
    cur.execute("ALTER USER projectnotes_user WITH PASSWORD 'mpcdbadm';")
    print("Successfully changed password for projectnotes_user.")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Failed to update password: {e}")
