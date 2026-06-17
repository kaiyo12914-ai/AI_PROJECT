from __future__ import annotations

import os
import re
import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from webapps.vanna.models import DataSource, FailedQueryRecord, TrainingExample, ExampleEmbedding
from webapps.vanna.sql_guard import validate_sql

def _detect_column_for_variable(sql: str, var_name: str) -> str:
    """
    Detect the column associated with a variable name in SQL.
    e.g. emp.deptno like :as_deptno -> deptno
    """
    # 模式一：欄位在左
    p1 = re.compile(rf"\b([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)\s*(?:=|like)\s*:{var_name}\b", re.IGNORECASE)
    m1 = p1.search(sql)
    if m1:
        col = m1.group(1)
        return col.split(".")[-1].strip()
    
    # 模式二：欄位在右
    p2 = re.compile(rf"\b:{var_name}\s*(?:=|like)\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)\b", re.IGNORECASE)
    m2 = p2.search(sql)
    if m2:
        col = m2.group(1)
        return col.split(".")[-1].strip()
    
    # 模式三：名稱推導猜測
    guess = var_name.lower()
    if guess.startswith("as_"):
        guess = guess[3:]
    return guess

def _extract_tables_from_sql(sql: str) -> list[str]:
    """
    Extract table names referenced in the SQL.
    """
    tables = []
    # 搜尋 FROM 後的資料表
    p = re.compile(r"\bfrom\s+([a-zA-Z0-9_@\.,\s]+?)(?:\bwhere\b|\bgroup\b|\border\b|\bunion\b|\bselect\b|\bjoin\b|$)", re.IGNORECASE | re.DOTALL)
    m = p.search(sql)
    if m:
        from_part = m.group(1)
        for part in from_part.split(","):
            tokens = part.strip().split()
            if tokens:
                t_token = tokens[0]
                t_name = t_token.split("@")[0].strip()
                if t_name:
                    tables.append(t_name.upper())
    
    # 搜尋 JOIN 後的資料表
    p_join = re.finditer(r"\bjoin\s+([a-zA-Z0-9_@]+)", sql, re.IGNORECASE)
    for mj in p_join:
        t_token = mj.group(1).split("@")[0].strip()
        if t_token:
            tables.append(t_token.upper())
            
    return list(set(tables))

def _lookup_column_metadata(column_name: str, sql_tables: list[str]) -> tuple[str, str] | None:
    """
    Lookup table_name and data_type for a column using the data_dictionary table.
    """
    column_name = (column_name or "").strip()
    with connection.cursor() as cursor:
        # 檢查 data_dictionary 表是否存在，避免拋錯
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'data_dictionary'
            );
        """)
        if not cursor.fetchone()[0]:
            return None

        # 優先比對 SQL 中出現 of table
        if sql_tables:
            sql_tables_cleaned = [t.strip().upper() for t in sql_tables if t.strip()]
            placeholders = ",".join(["%s"] * len(sql_tables_cleaned))
            query = f"""
                SELECT table_name, data_type 
                FROM data_dictionary 
                WHERE TRIM(UPPER(column_name)) = %s 
                AND TRIM(UPPER(table_name)) IN ({placeholders})
                LIMIT 1
            """
            cursor.execute(query, [column_name.upper()] + sql_tables_cleaned)
            row = cursor.fetchone()
            if row:
                return row[0].strip(), row[1].strip()
        
        # Fallback 模糊搜尋
        cursor.execute("""
            SELECT table_name, data_type 
            FROM data_dictionary 
            WHERE TRIM(UPPER(column_name)) = %s 
            LIMIT 1
        """, [column_name.upper()])
        row = cursor.fetchone()
        if row:
            return row[0].strip(), row[1].strip()
            
    return None

class Command(BaseCommand):
    help = "Autofix failed queries by replacing variables with actual values from db and correcting questions using LLM."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview fixes and questions without saving to database.",
        )
        parser.add_argument(
            "--auto-approve",
            action="store_true",
            help="Automatically transfer successful fixes to TrainingExample.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit the number of records processed.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        auto_approve = options["auto_approve"]
        limit = options["limit"]

        self.stdout.write(self.style.NOTICE("Fetching pending FailedQueryRecord records..."))
        records = FailedQueryRecord.objects.filter(status="pending").order_type = ["id"]
        # Django model filtering ordered by id
        records = FailedQueryRecord.objects.filter(status="pending").order_by("id")

        if limit > 0:
            records = records[:limit]

        if not records:
            self.stdout.write(self.style.SUCCESS("No pending failed query records found."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(records)} records to process."))

        # Initialize LLM model
        self.stdout.write(self.style.NOTICE("Initializing LLM Chat Model..."))
        try:
            from webapps.llm.llm_factory import get_chat_model
            chat_model = get_chat_model()
            self.stdout.write(self.style.SUCCESS("LLM model loaded successfully."))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Could not load LLM Chat Model: {exc}"))
            return

        # Initialize Embedding model for auto-approve
        embeddings_impl = None
        model_name = ""
        if auto_approve and not dry_run:
            self.stdout.write(self.style.NOTICE("Initializing Shared Embedding Model for auto-approve..."))
            try:
                from webapps.llm.embedding_factory import get_shared_embedding_model, get_shared_embedding_model_name
                embeddings_impl = get_shared_embedding_model()
                model_name = get_shared_embedding_model_name()
                self.stdout.write(self.style.SUCCESS(f"Embedding model loaded: {model_name}"))
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Could not load embedding model: {exc}. Auto-approve will skip immediate embedding calculation."))

        fixed_count = 0
        skipped_count = 0

        for r in records:
            rec_id = r.id
            question = r.question or ""
            sql_text = r.failed_sql or ""
            ds_code = r.data_source_code or ""

            self.stdout.write(self.style.NOTICE(f"\nProcessing Record ID={rec_id}: {question[:60]}"))

            # 1. 搜尋所有冒號變數
            variables = list(set(re.findall(r":([a-zA-Z_]\w*)", sql_text)))
            if not variables:
                self.stdout.write(self.style.WARNING(f"  No variables detected in SQL. Skipping."))
                skipped_count += 1
                continue

            self.stdout.write(self.style.NOTICE(f"  Detected variables: {variables}"))
            
            # 取得資料來源對應的 db_profile
            ds = DataSource.objects.filter(code=ds_code).first()
            db_type = ds.db_type if ds else "oracle"
            if ds and ds.db_profile:
                profile = ds.db_profile
            else:
                profile = "projectnotes" if db_type == "postgresql" else "ERP_205"
            sql_tables = _extract_tables_from_sql(sql_text)

            var_mapping = {}
            mapping_failed = False

            # 2. 針對各個變數尋找實際值
            for var in variables:
                col_name = _detect_column_for_variable(sql_text, var)
                meta = _lookup_column_metadata(col_name, sql_tables)
                
                if not meta:
                    db_dict_exists = False
                    db_dict_rows = 0
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_schema = 'public' 
                                AND table_name = 'data_dictionary'
                            );
                        """)
                        db_dict_exists = cursor.fetchone()[0]
                        if db_dict_exists:
                            cursor.execute("SELECT COUNT(*) FROM public.data_dictionary;")
                            db_dict_rows = cursor.fetchone()[0]

                    db_dict_status = f"public.data_dictionary exists (rows: {db_dict_rows})" if db_dict_exists else "public.data_dictionary DOES NOT EXIST!"
                    
                    self.stdout.write(self.style.WARNING(
                        f"  [ERROR-METADATA] Could not find column metadata for variable '{var}' (column '{col_name}'). Skipping record.\n"
                        f"  Debug Info:\n"
                        f"    - DB Source: {ds_code} (type: {db_type}, profile: {profile})\n"
                        f"    - SQL Reference Tables: {sql_tables}\n"
                        f"    - Searching Field: '{col_name}'\n"
                        f"    - Data Dictionary Status: {db_dict_status}"
                    ))
                    mapping_failed = True
                    break

                table_name, data_type = meta
                self.stdout.write(self.style.NOTICE(f"  Variable '{var}' -> Column: {col_name}, Table: {table_name}, Type: {data_type}"))

                # 實體查詢取得一個真實值
                if db_type == "oracle":
                    query_sql = f"SELECT {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL AND ROWNUM <= 1"
                else:
                    query_sql = f"SELECT {col_name} FROM {table_name} WHERE {col_name} IS NOT NULL LIMIT 1"

                actual_val = None
                try:
                    from webapps.database.db_factory import db_query_one
                    row_val = db_query_one(db_type, query_sql, profile=profile)
                    if row_val is not None:
                        # 處理 MockRow 或是 tuple/dict 的包裝
                        if hasattr(row_val, "_order") and row_val._order:
                            actual_val = row_val[row_val._order[0]]
                        elif isinstance(row_val, (tuple, list)):
                            actual_val = row_val[0]
                        elif isinstance(row_val, dict):
                            actual_val = list(row_val.values())[0]
                        else:
                            actual_val = row_val
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(f"  Database query failed for column '{col_name}': {exc}"))

                if actual_val is None:
                    env_mode = (os.getenv("ENV") or "").strip().upper()
                    if env_mode in ("EXT", "DEV", "LOCAL", "TEST", "CI"):
                        c_lower = col_name.lower()
                        if "dept" in c_lower or "dep" in c_lower:
                            actual_val = "01"
                        elif "emp" in c_lower or "pers" in c_lower:
                            actual_val = "E00001"
                        elif "year" in c_lower:
                            actual_val = "115"
                        elif "date" in c_lower:
                            actual_val = "20260617"
                        elif "orno" in c_lower or "ord" in c_lower or "no" in c_lower:
                            actual_val = "1150001"
                        else:
                            actual_val = "TEST_VAL"
                        self.stdout.write(self.style.WARNING(f"  [Fallback-EXT] Mocking actual value for column '{col_name}' -> '{actual_val}'"))
                    else:
                        self.stdout.write(self.style.WARNING(f"  Could not fetch actual value from table '{table_name}' for variable '{var}'. Skipping record."))
                        mapping_failed = True
                        break

                # 依據資料型態包裝值
                dt_upper = data_type.upper()
                is_str = any(x in dt_upper for x in ["CHAR", "TEXT", "VARCHAR", "DATE", "TIME", "TIMESTAMP"])
                
                if is_str:
                    formatted_val = f"'{actual_val}'"
                else:
                    formatted_val = str(actual_val)

                var_mapping[var] = (actual_val, formatted_val)

            if mapping_failed:
                skipped_count += 1
                continue

            # 3. 進行 SQL 中的變數替換
            fixed_sql = sql_text
            mapping_str_list = []
            for var, (raw_val, formatted_val) in var_mapping.items():
                fixed_sql = re.sub(rf":{var}\b", formatted_val, fixed_sql, flags=re.IGNORECASE)
                mapping_str_list.append(f":{var} = {raw_val} ({formatted_val})")

            variable_mapping_str = ", ".join(mapping_str_list)
            self.stdout.write(self.style.SUCCESS(f"  Successfully fixed SQL: {fixed_sql}"))

            # 4. 呼叫 LLM 修正自然提問
            self.stdout.write(self.style.NOTICE("  Invoking LLM to correct question..."))
            prompt = f"""你是一位自然語言處理與資料庫專家。
我們正在將一筆失敗的 SQL 語法精進為可執行的 SQL，並同步修正其自然語言提問（Question），使其與新的 SQL 語意完全一致，以作為 AI 訓練範例。

【原始提問】：{question}
【原始 SQL】：{sql_text}
【變數與實際值的對應關係】：{variable_mapping_str}
【修改後的可執行 SQL】：{fixed_sql}

請根據修改後的 SQL 與變數實際值，將原始提問中抽象的變數描述（例如「指定服務單位」、「某員工」、「特定年度」、「指定廠別」）替換為實際帶入的具體值，使其成為一個具體且語意完整的提問。

規範：
1. 必須保留業務前綴（如 [人事] 或 [採購]）。
2. 請僅輸出修正後的提問文字，不要包含任何額外的解釋、引號或 Markdown 格式。
"""
            try:
                res = chat_model.invoke(prompt)
                fixed_question = res.content.strip().replace('"', '').replace("'", "")
                self.stdout.write(self.style.SUCCESS(f"  Original question: {question}"))
                self.stdout.write(self.style.SUCCESS(f"  Fixed question:    {fixed_question}"))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  LLM call failed: {exc}. Retaining original question."))
                fixed_question = question

            # 5. 安全性驗證與更新
            is_safe, error_msg = validate_sql(fixed_sql)
            if not is_safe:
                self.stdout.write(self.style.WARNING(f"  Warning: Fixed SQL failed SQL Guard validation: {error_msg}"))
            
            if dry_run:
                self.stdout.write(self.style.SUCCESS("  [Dry-Run] Check complete. No changes written."))
                fixed_count += 1
                continue

            # 實體寫入 / 轉移
            if auto_approve and is_safe and ds:
                self.stdout.write(self.style.NOTICE("  Transferring to TrainingExample and ExampleEmbedding..."))
                try:
                    with transaction.atomic():
                        te, created = TrainingExample.objects.get_or_create(
                            data_source=ds,
                            question=fixed_question,
                            defaults={
                                "sql_text": fixed_sql,
                                "review_status": "approved",
                                "created_by": "autofix_command"
                            }
                        )
                        if not te.embeddings.exists() and embeddings_impl:
                            vector = embeddings_impl.embed_query(fixed_question)
                            ExampleEmbedding.objects.create(
                                training_example=te,
                                data_source=ds,
                                question_text=fixed_question,
                                sql_text=fixed_sql,
                                embedding=vector,
                                embedding_model=model_name
                            )
                        
                        # 刪除原 FailedQueryRecord 記錄
                        r.delete()
                    self.stdout.write(self.style.SUCCESS(f"  Record ID={rec_id} successfully converted to approved TrainingExample."))
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"  Failed to transfer record to training set: {exc}"))
                    skipped_count += 1
                    continue
            else:
                # 僅就地更新 Failed 記錄的 SQL 與 Question
                r.failed_sql = fixed_sql
                r.question = fixed_question
                r.save()
                self.stdout.write(self.style.SUCCESS(f"  Record ID={rec_id} updated in nl2sql_failed_query_record."))

            fixed_count += 1

        self.stdout.write(self.style.SUCCESS(f"\nProcessing complete: Fixed={fixed_count}, Skipped={skipped_count}"))






# ## 💡 內網使用執行指南

# 在內網正式環境（`ENV=INT`，實體 Oracle 連線正常）時，管理員可以使用以下方式來執行此清洗工具：

# 1. **預覽模式 (Dry-Run)**：
#    先預覽前 10 筆記錄的清洗與替換成果，不寫入資料庫：
#    ```bash
#    python manage.py autofix_failed_queries --dry-run --limit 10
#    ```

# 2. **就地更新模式**：
#    實際替換變數並讓 LLM 修正問題，更新在 `nl2sql_failed_query_record` 中（狀態仍為 `pending`），方便管理員在 Vanna UI 的「Failed Query」頁籤進行確認：
#    ```bash
#    python manage.py autofix_failed_queries --limit 50
#    ```

# 3. **全自動核准轉移模式**：
#    自動替換變數與修正問句。若修正後的 SQL 語法能通過 SQL Guard 的安全性審查，則**直接自動轉移**至正式的 `TrainingExample` (SQL approved examples) 中並即時計算 Embedding 向量，同時將原 Failed 記錄從庫中清除，實現一鍵全自動數據淨化：
#    ```bash
#    python manage.py autofix_failed_queries --auto-approve --limit 100
