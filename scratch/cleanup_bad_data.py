import psycopg2
conn = psycopg2.connect('postgresql://projectnotes_user:mpcdbadm@192.168.0.137:5432/projectnotes')
cur = conn.cursor()

# Delete records where the prompt is a translation prompt but the mode is NOT translation
sql1 = "DELETE FROM englishchat_question_bank WHERE mode != 'translation' AND (prompt_text ILIKE '%%Translate:%%' OR prompt_text ILIKE '%%Translate %%');"

# Delete records where the mode is fill_blank but there's no blank (____) in the prompt
sql2 = "DELETE FROM englishchat_question_bank WHERE mode = 'fill_blank' AND prompt_text NOT LIKE '%%____%%';"

# Delete records where choices_json is empty for fill_blank
sql3 = "DELETE FROM englishchat_question_bank WHERE mode = 'fill_blank' AND (choices_json::text = '[]' OR choices_json IS NULL);"

# Delete records where words_json is empty for reorder
sql4 = "DELETE FROM englishchat_question_bank WHERE mode = 'reorder' AND (words_json::text = '[]' OR words_json IS NULL);"

for sql in [sql1, sql2, sql3, sql4]:
    cur.execute(sql)
    print(f"Deleted {cur.rowcount} rows with query: {sql}")

conn.commit()
conn.close()
