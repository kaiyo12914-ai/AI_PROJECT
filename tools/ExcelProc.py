import os
import pandas as pd
import oracledb
#from dotenv import load_dotenv
import re

# 1. 讀取環境變數與資料庫連線設定
#load_dotenv()
#ORA_USER = os.getenv("user")
#ORA_PASS = os.getenv("password")
#ORA_HOST = os.getenv("host")
#ORA_PORT = os.getenv("port")
#ORA_SERVICE_NAME = os.getenv("service_name")

# 預設檔名定義
DEFAULT_TEL_FILE = 'MPC電話表.xls'
DEFAULT_CONTACT_FILE = '單位人員連絡冊.xlsx'
DEFAULT_EXPORT_FILE = '中心計資組人事資訊.xlsx'

def get_conn():
    host = os.getenv("ORA_HOST")
    port = os.getenv("ORA_PORT")
    service = os.getenv("ORA_SERVICE_NAME")
    user = os.getenv("ORA_USER")
    password = os.getenv("ORA_PASS")

    missing = [k for k, v in {
        "ORA_HOST": host,
        "ORA_PORT": port,
        "ORA_SERVICE_NAME": service,
        "ORA_USER": user,
        "ORA_PASS": password,
    }.items() if not v]

    if missing:
        raise RuntimeError("資料庫連線失敗：缺少環境變數 " + ", ".join(missing))

    try:
        dsn = oracledb.makedsn(host=host, port=int(port), service_name=service)
        return oracledb.connect(user=user, password=password, dsn=dsn)

    except oracledb.Error as e:
        # ✅ 解包錯誤（oracledb 的標準寫法）
        err = e.args[0] if e.args else None
        code = getattr(err, "code", None)
        msg = getattr(err, "message", None) or str(e)

        # ✅ 依 code 給更友善訊息（你要的「連線失敗訊息」）
        friendly = oracle_friendly_message(code, msg)

        raise RuntimeError(friendly)  # 給 views.py 統一回傳 JSON



def clean_phone(phone_str):
    """提取電話號碼的整數部分前20位"""
    if pd.isna(phone_str) or not phone_str:
        return ""

    str_val = str(phone_str).strip()

    # 處理科學符號或浮點數
    try:
        if 'e' in str_val.lower():
            num_value = float(str_val)
            return f"{num_value:.0f}"[:20]
        elif '.' in str_val:
            integer_part, *rest = str_val.split('.')
            return clean_phone(integer_part)[:20]
    except ValueError:
        pass

    cleaned = ''.join(re.findall(r'\d+', str_val))
    return cleaned[:10]

def process_value(value):
    """處理各種資料類型轉換為字串"""
    if pd.isna(value) or value is None:
        return ""

    # 處理浮點數
    try:
        if isinstance(value, float) and 'e' in str(value).lower():
            num_value = float(str(value))
            return clean_phone(f"{num_value:.0f}")
        elif isinstance(value, float):
            return f"{int(value)}"
    except ValueError:
        pass

    # 一般字串處理
    if isinstance(value, (str, int)):
        return str(value).strip()
    else:
        try:
            return str(float(value)).strip()
        except (ValueError, TypeError):
            return ""

def import_contact_data(excel_file=None):
    """匯入人員連絡冊資料到CT_EMPLOY表"""
    excel_file = excel_file or DEFAULT_CONTACT_FILE
    try:
        # 讀取Excel附件，使用預設編碼
        excel_df = pd.read_excel(excel_file, dtype=str)

        conn = get_conn()
        if not conn:
            return False

        cursor = None
        try:
            cursor = conn.cursor()
            results = []

            for index, row in excel_df.iterrows():
                try:
                    update_sql = """
                        UPDATE CT_EMPLOY SET
                            IDNO = :id,
                            NAME = :name,
                            ADRSS = :adrss,
                            PADRS = :padrs,
                            TELNO = TO_CHAR(:telno),
                            HANDTELE = TO_CHAR(:handtele),
                            INNERTELE = TO_CHAR(:innertele),
                            CNTPSN = :cntpsn,
                            CHTELNO = TO_CHAR(:chtele),
                            CARNO = :carno,
                            MOTONO = :motono ,
                            BLOODTYPE=:bloodtype,
                            ENGLISH_NAME=:english_name
                        WHERE IDNO = :id
                    """

                    data = {
                        'id': process_value(row.get('ID', '')),
                        'name': process_value(row.get('姓名', '')),
                        'adrss': process_value(row.get('住址', ''))[:250],
                        'padrs': process_value(row.get('戶籍地址', ''))[:250],
                        'telno': clean_phone(process_value(row.get('電話', ''))) if '電話' in row else "",
                        'handtele': clean_phone(process_value(row.get('手機', ''))) if '手機' in row else "",
                        'innertele': clean_phone(process_value(row.get('軍用電話', ''))) if '軍用電話' in row else "",
                        'cntpsn': process_value(row.get('連絡人', ''))[:100],
                        'chtele': clean_phone(process_value(row.get('連絡電話', ''))) if '連絡電話' in row else "",
                        'carno': process_value(row.get('汽車車號', ''))[:20],
                        'motono': process_value(row.get('機車車號', ''))[:20],
                        'bloodtype': process_value(row.get('血型', ''))[:20],
                        'english_name': process_value(row.get('英文姓名', ''))[:20]
                    }

                    if not data['id']:
                        print(f"第 {index+1} 筆資料缺少ID，跳過處理")
                        continue

                    # 檢查記錄是否存在
                    cursor.execute("SELECT COUNT(*) FROM CT_EMPLOY WHERE IDNO = :id", id=data['id'])
                    exists = cursor.fetchone()[0] > 0

                    result_row = {
                        'ID': data['id'],
                        '姓名': data['name'],
                        '結果': ''
                    }

                    if exists:
                        try:
                            # 直接使用原始值，由Oracle處理編碼轉換
                            cursor.execute(update_sql, data)
                            print(f"成功更新第 {index+1} 筆資料: ID={data['id']}")
                            result_row['結果'] = '更新成功'
                        except oracledb.DatabaseError as e:
                            error, = e.args
                            if error.code == 2049:
                                print(f"第 {index+1} 筆資料更新失敗，欄位值過長 - ID={data['id']}")
                                result_row['結果'] = '更新失敗 (欄位值過長)'
                            else:
                                print(f"第 {index+1} 筆資料更新時發生錯誤: {error.message}")
                                conn.rollback()
                                result_row['結果'] = f'更新失敗 ({error.message})'
                    else:
                        print(f"第 {index+1} 筆資料ID不存在 - ID={data['id']}")
                        result_row['結果'] = 'ID不存在'

                    results.append(result_row)

                except Exception as e:
                    print(f"處理第 {index+1} 筆資料時發生錯誤: {str(e)}")
                    conn.rollback()
                    if results and isinstance(results[-1], dict):
                        results[-1]['結果'] += f", 錯誤: {str(e)}"
                    else:
                        results.append({
                            'ID': data.get('id', 'N/A'),
                            '姓名': data.get('name', 'N/A'),
                            '結果': f'錯誤: {str(e)}'
                        })

            conn.commit()
            print("所有資料處理完成")

            # 生成報告
            output_file = '匯入資料更新結果.xlsx'
            results_df = pd.DataFrame(results)

            try:
                with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                    results_df.to_excel(writer, sheet_name='更新結果', index=False)
                    excel_df.to_excel(writer, sheet_name='原始資料', index=False)

                print(f"更新結果已保存至 {output_file}，包含兩個工作表：'更新結果'和'原始資料'")
            except Exception as e:
                print(f"生成Excel報告時發生錯誤: {str(e)}")

        except oracledb.DatabaseError as e:
            error, = e.args
            print(f"資料庫操作時發生錯誤: {error.message}")
            conn.rollback()
        finally:
            if cursor and hasattr(cursor, 'close'):
                cursor.close()
            if conn and hasattr(conn, 'close'):
                conn.close()

        return True

    except Exception as e:
        print(f"執行過程中發生錯誤: {str(e)}")
        if 'conn' in locals() and conn and hasattr(conn, 'rollback'):
            conn.rollback()
        return False

def clean_name(name):
    """處理姓名中的空格：刪除全部空格"""
    if pd.isna(name) or not name:
        return ""
    # 如果是中文名（包含中文字），刪除所有空格
    has_chinese = any(char in '。，、；：？（）《》“”【】{}[]<>;:?"' for char in str(name))
    if has_chinese:
        return str(name).replace(' ', '')
    # 如果是英文名或其他類型，保留一個空格
    else:
        return ' '.join(str(name).split())

def clean_phone_v2(phone_str):
    """提取電話號碼的整數部分前六位"""
    if pd.isna(phone_str) or not phone_str:
        return ""

    # 移除所有非數字符號
    cleaned = ''.join(re.findall(r'\d+', str(phone_str)))

    # 如果是浮點數（如655960.0），取前面的整數部分
    if '.' in phone_str:
        integer_part = cleaned.split('.')[0]
    else:
        integer_part = cleaned

    # 取前六位數字，若長度不足則全部保留
    return (integer_part + '0' * 6)[:6]  # 確保至少有六位數字

def update_db_name(name, phone):
    """當附件姓名與DB姓名相同時更新INNERTELE"""
    conn = None
    cursor = None
    try:
        conn = get_conn()
        if not conn:
            return False

        cursor = conn.cursor()

        # 先查詢確認是否存在相同姓名
        query = """
            SELECT INNERTELE, NAME FROM CT_EMPLOY WHERE TRIM(NAME) = :name_param
        """
        cursor.execute(query, name_param=name)
        db_result = cursor.fetchone()

        if not db_result:
            return False

        # 更新INNERTELE
        update_query = """
            UPDATE CT_EMPLOY
            SET INNERTELE = :phone_param
            WHERE TRIM(NAME) = :name_param
        """
        cursor.execute(update_query, phone_param=phone, name_param=name)
        conn.commit()

        # 同步更新CT_EMPLOY_SIMPLE表
        update_query1 = """
            UPDATE CT_EMPLOY_SIMPLE
            SET INNERTELE = :phone_param
            WHERE TRIM(NAME) = :name_param
        """
        cursor.execute(update_query1, phone_param=phone, name_param=name)
        conn.commit()

        return True

    except Exception as e:
        print(f"更新資料庫時發生錯誤: {str(e)}")
        if conn and hasattr(conn, 'rollback'):
            conn.rollback()
        return False
    finally:
        try:
            if cursor and hasattr(cursor, 'close'):
                cursor.close()
            if conn and hasattr(conn, 'close'):
                conn.close()
        except Exception as e:
            print(f"關閉連線時發生錯誤: {str(e)}")

def compare_data(excel_file=None):
    """比對電話表資料與資料庫，更新不一致的記錄"""
    excel_file = excel_file or DEFAULT_TEL_FILE
    # 定義輸出清單結構
    output_list = []

    try:
        # 讀取Excel附件
        excel_df = pd.read_excel(excel_file)

        for index in range(1, len(excel_df)):
            row_data = excel_df.iloc[index]

            # 提取階級與姓名（假設Excel結構為：階級1, 姓名1, 電話1...）
            for i in [1, 4, 7, 10, 13]:  # 假設每個人員資料間隔3格
                level_col = excel_df.columns[i-1] if (i-1) < len(excel_df.columns) else None
                name_col = excel_df.columns[i] if i < len(excel_df.columns) else None
                phone_col = excel_df.columns[i+1] if (i+1) < len(excel_df.columns) else None

                # 避免超出索引
                if not all([level_col, name_col, phone_col]):
                    continue

                level = process_value(row_data[level_col]) if pd.notna(row_data[level_col]) else ""
                raw_name = process_value(row_data[name_col]) if pd.notna(row_data[name_col]) else ""

                # 處理姓名欄位：處理中間空格
                name = clean_name(raw_name) if raw_name else ""

                phone = clean_phone_v2(str(row_data[phone_col])) if pd.notna(row_data[phone_col]) else ""

                # 如果姓名不為空則進行比對
                if name:
                    conn = get_conn()
                    if not conn:  # 檢查連線是否成功建立
                        continue

                    cursor = None
                    try:
                        cursor = conn.cursor()

                        query = """
                            SELECT INNERTELE, NAME
                            FROM CT_EMPLOY
                            WHERE TRIM(NAME) = :name_param
                        """
                        cursor.execute(query, name_param=name)
                        db_result = cursor.fetchone()

                        if db_result:
                            db_phone = str(db_result[0]) if db_result[0] else "未找到"
                            db_name = db_result[1]

                            # 如果附件姓名與DB姓名相同且電話不同，則更新
                            if name == db_name and phone != db_phone:
                                print(f"發現不一致的記錄: {name}")
                                if update_db_name(name, phone):
                                    print(f"成功更新{name}的電話號碼至資料庫")
                                else:
                                    print(f"更新{name}的電話號碼時失敗")

                            output_list.append({
                                '階級': level,
                                '附件姓名': name,
                                'DB姓名': db_name if db_name else "無此人",
                                '附件電話': phone,
                                'DB電話': db_phone,
                                '比對狀態': "相符" if str(phone).isdigit() and phone == db_phone else "不相符"
                            })

                        else:
                            output_list.append({
                                '階級': level,
                                '附件姓名': name,
                                'DB姓名': "無此人",
                                '附件電話': phone,
                                'DB電話': "未找到",
                                '比對狀態': "不相符"
                            })

                    except Exception as e:
                        print(f"處理{name}時發生錯誤: {str(e)}")
                        output_list.append({
                            '階級': level,
                            '附件姓名(處理後)': name,
                            'DB姓名': "查詢失敗",
                            '附件电话': phone,
                            'DB电话': "查詢失敗",
                            '比對狀態': "錯誤"
                        })
                    finally:
                        if cursor and hasattr(cursor, 'close'):
                            cursor.close()
                        if conn and hasattr(conn, 'close'):
                            conn.close()

        # 輸出結果
        output_df = pd.DataFrame(output_list)
        try:
            output_df.to_excel('人員電話比對結果.xlsx', index=False)
            print("比對完成，結果已匯出至 '人員電話比對結果.xlsx'")
        except Exception as e:
            print(f"匯出Excel時發生錯誤: {str(e)}")

    except Exception as e:
        print(f"執行過程中發生錯誤: {str(e)}")

def export_mpc_employee_data(output_file=None):
    """匯出計資組人事資訊到Excel"""
    output_file = output_file or DEFAULT_EXPORT_FILE
    try:
        conn = get_conn()
        if not conn:
            return False

        cursor = None
        try:
            cursor = conn.cursor()

            query = """
            SELECT
               d.DEPT_NAME AS "單位",
               r.RANK AS "編階",
               j.JOB AS "職稱",
               e.NAME AS "姓名",
               TO_CHAR(e.DTE_BTH, 'YYYY/MM/DD') AS "生日",
               e.IDNO AS "ID",
               TO_CHAR(e.DTE_ARMY, 'YYYY/MM/DD') AS "入伍日期",
               e.ADRSS AS "住址",
               e.PADRS AS "戶籍地址",
               e.TELNO AS "電話",
               e.HANDTELE AS "手機",
               e.INNERTELE AS "軍用電話",
               e.CNTPSN AS "連絡人",
               e.CHTELNO AS "連絡電話",
               e.CARNO AS "汽車車號",
               e.MOTONO AS "機車車號",
               s.ORDERCODE AS "ORDERCODE",
               r.SEQ AS "ORDERSEQ"
            FROM
               CT_EMPLOY e
            LEFT JOIN TT_DEPT_CODE d ON e.DEPTNO = d.DEPT_CODE
            LEFT JOIN CT_RANK r ON e.RNKNO = r.RNKNO
            LEFT JOIN CT_JOB j ON e.JOBNO = j.JOBNO
            LEFT JOIN CT_SPECIALID s ON e.IDNO = s.IDNO
            WHERE
               e.SVCTNO = '00'
               AND e.FACTORY_PLANT = 'MPC'
               AND e.DEPTNO = 'EA'
               AND LENGTH(TRIM(e.IDNO))=10
            ORDER BY
               r.SEQ, s.ORDERCODE
            """

            cursor.execute(query)
            results = cursor.fetchall()

            column_names = [desc[0] for desc in cursor.description]
            df = pd.DataFrame(results, columns=column_names)

            with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='人員資料', index=False)
                print(f"人員資料已成功匯出至 {output_file}")

        except oracledb.DatabaseError as e:
            error, = e.args
            print(f"資料庫操作時發生錯誤: {error.message}")
            conn.rollback()
            return False

    except Exception as e:
        print(f"匯出資料時發生錯誤: {str(e)}")
        if 'ORA-00933' in str(e):
            print("錯誤原因：SQL查詢中包含不正確的語法結構，已修改為標準形式")
        return False
    finally:
        try:
            if cursor and hasattr(cursor, 'close'):
                cursor.close()
            if conn and hasattr(conn, 'close'):
                conn.close()
        except Exception as e:
            print(f"關閉連線時發生錯誤: {str(e)}")

def main():
    """主程式入口"""
    while True:
        try:
            # 顯示選單
            print("\n===== 中心人事資料管理系統 =====")
            print("1. 電話表匯入")
            print("2. 人事資訊匯入")
            print("3. 計資組人事資訊匯出")
            print("0. 退出")

            choice = input("\n請選擇操作模式 (1/2/3/0): ").strip()

            if choice == '1':
                confirm = input(f"將使用預設檔名 '{DEFAULT_TEL_FILE}'，是否繼續？(y/n): ").lower()
                if confirm in ['y', 'yes']:
                    compare_data()
                else:
                    excel_file = input("請輸入中心電話表Excel檔案名稱（包含副檔名）：").strip()
                    compare_data(excel_file)
            elif choice == '2':
                confirm = input(f"將使用預設檔名 '{DEFAULT_CONTACT_FILE}'，是否繼續？(y/n): ").lower()
                if confirm in ['y', 'yes']:
                    import_contact_data()
                else:
                    excel_file = input("請輸入人員連絡冊Excel檔案名稱（包含副檔名）：").strip()
                    import_contact_data(excel_file)
            elif choice == '3':
                print("\n確定要匯出計資組人事資訊嗎？")
                confirm = input(f"將使用預設檔名 '{DEFAULT_EXPORT_FILE}'，是否繼續？(y/n): ").lower()
                if confirm in ['y', 'yes']:
                    export_mpc_employee_data()
            elif choice == '0':
                print("\n感謝使用，程式結束")
                break
            else:
                print("無效選項，請重新輸入")

        except KeyboardInterrupt:
            print("\n程式被中斷，即將退出...")
            break
        except Exception as e:
            print(f"發生錯誤: {str(e)}")
            continue

if __name__ == "__main__":
    main()