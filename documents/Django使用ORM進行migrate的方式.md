# 擴充方式記錄
建立`evaluation.py`作為資料庫模型，之後用以下指令讓ORM可以自已建立資料表：
```bash
python manage.py makemigrations comment  # 生成遷移檔案
python manage.py migrate              # 執行遷移，建立資料表
python manage.py migrate comment

sqlite3 db.sqlite3 ".tables"  # 查看是否已生成 comment_evaluation 資料表
```
如果有再更新欄位，就再執行一次上面的指令，sqlite3檔案內的table schema會自動更新。