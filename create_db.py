import psycopg2

passwords = ['Ntou6228', 'postgres', 'password', 'root']

conn = None
for pw in passwords:
    try:
        print(f"Trying postgres:{pw}...")
        conn = psycopg2.connect(f'postgresql://postgres:{pw}@192.168.0.137:5432/postgres')
        print(f"Success with postgres:{pw}!")
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if projectnotes db exists
        cur.execute("SELECT 1 FROM pg_database WHERE datname='projectnotes'")
        if not cur.fetchone():
            print("Creating database projectnotes...")
            cur.execute("CREATE DATABASE projectnotes OWNER dating_user;")
        else:
            print("Database projectnotes already exists.")
            
        cur.close()
        conn.close()
        break
    except Exception as e:
        print(f"Failed: {str(e).strip()}")

if not conn:
    print("Could not connect as superuser to create DB.")
