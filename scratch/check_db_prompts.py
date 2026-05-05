import psycopg2
conn = psycopg2.connect('postgresql://projectnotes_user:mpcdbadm@192.168.0.137:5432/projectnotes')
cur = conn.cursor()
cur.execute("SELECT question_id, mode, prompt_text, choices_json FROM englishchat_question_bank WHERE prompt_text LIKE '%Translate:%' OR prompt_text LIKE '%translate:%' LIMIT 10")
rows = cur.fetchall()
for r in rows:
    print(r)
