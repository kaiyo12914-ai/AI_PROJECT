import psycopg2

try:
    conn = psycopg2.connect('postgresql://postgres:Ntou6228@192.168.0.137:5432/postgres')
    conn.autocommit = True
    cur = conn.cursor()
    
    # 建立新使用者 (如果尚未存在)
    try:
        cur.execute("CREATE USER projectnotes_user WITH PASSWORD 'Ntou6228';")
        print("Created user projectnotes_user")
    except psycopg2.errors.DuplicateObject:
        print("User projectnotes_user already exists")
    except Exception as e:
        print(f"Error creating user: {e}")
        conn.rollback()

    # 變更資料庫擁有權
    cur.execute("ALTER DATABASE projectnotes OWNER TO projectnotes_user;")
    print("Successfully changed owner of projectnotes database to projectnotes_user.")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Failed to update owner: {e}")
