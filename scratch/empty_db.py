import psycopg2
conn = psycopg2.connect('postgresql://projectnotes_user:mpcdbadm@192.168.0.137:5432/projectnotes')
cur = conn.cursor()

cur.execute("DELETE FROM englishchat_question_bank;")
print(f"Cleared {cur.rowcount} questions from the database.")

conn.commit()
conn.close()
