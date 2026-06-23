# SQL 語法不完整之失敗語法精進記錄清單

本報告列出 `nl2sql_failed_query_record` 資料表中所有 `failed_sql` 欄位語法不完整或無法直接執行的紀錄，共發現 **45** 筆（總 Failed 記錄筆數：1383）。

## 記錄 ID: 295
* **自然語言提問**: [人事] 查詢指定年度所有軍職人員的身份證字號姓名單位代碼及職等資料
* **判定為不完整的原因**: 括號不匹配 (左括號 2 個，右括號 3 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select distinct bpa.idno empno ,em.name name ,'' dept_name ,em.deptno deptno ,em.rnkno -- ,'' rank -- ,em.factory_code -- ,em.adrss --上面兩個用空字串填的 column (rank跟dept_name) 是怕程式出錯加的欄位 --，至於為何不從下面表格撈，這就要問為何中心的資料庫真他媽的棒了:) --1. 有階級名稱不存在的 2. 也有沒單位代碼的 from ct_bonus_points_army bpa ,ct_employ_simple em -- ,ct_rank rnk -- ,tt_dept_code dc where substr(bpa.ym, 1, 4) - 1911 = :n_year and bpa.idno = em.empno order by em.deptno ,em.rnkno ,bpa.idno
```

---
## 記錄 ID: 455
* **自然語言提問**: [品保] 查詢已付款的帳用清單核對表包含傳票號碼付款憑證號碼金額年度月份日期及跨月資訊
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT warrant_num, voucher_num, money, year, mon, day, tmon FROM ( SELECT ~
```

---
## 記錄 ID: 464
* **自然語言提問**: [品保] 查詢各部門各經費代碼每月的非固定給與金額統計明細
* **判定為不完整的原因**: 括號不匹配 (左括號 3 個，右括號 1 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT DEPT_REF,FUNDS_CD,MON, SUM(AMOUNT) AS AMOUNT FROM ( SELECT substr(~
```

---
## 記錄 ID: 501
* **自然語言提問**: [生產] 查詢各產品類別於指定日期區間內各類耗料金額統計總表
* **判定為不完整的原因**: 括號不匹配 (左括號 148 個，右括號 146 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT MTYPE, PRODTYPE, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM YT_TRAN, JT_ORDWK, QT_PRJM WHERE ( yt_tran.tornu = jt_ordwk.oorno (+)) AND ( jt_ordwk.prjno = qt_prjm.prjno (+)) AND ( YT_TRAN.TMACO IN ('C3A')) AND ( TO_CHAR(TDATE, 'YYYYMMDD') - 19110000 BETWEEN :as_bgn_date AND :as_end_date) AND ( YT_TRAN.BGCODE IN ('Z')) AND ( QT_PRJM.PRODTYPE = JT_PRODTYPE.PRODTYPE) AND ( substr(uf_oorno_tail(yt_tran.tornu), 1, 1) NOT IN ('F'))), 0) AMTZ, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM YT_TRAN, JT_ORDWK, QT_PRJM WHERE ( yt_tran.tornu = jt_ordwk.oorno (+)) AND ( jt_ordwk.prjno = qt_prjm.prjno (+)) AND ( YT_TRAN.TMACO IN ('C3A')) AND ( TO_CHAR(TDATE, 'YYYYMMDD') - 19110000 BETWEEN :as_bgn_date AND :as_end_date) AND ( YT_TRAN.BGCODE IN ('G')) AND ( QT_PRJM.PRODTYPE = JT_PRODTYPE.PRODTYPE) AND ( substr(uf_oorno_tail(yt_tran.tornu), 1, 1) NOT IN ('F'))), 0) AMTG, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM YT_TRAN, JT_ORDWK, QT_PRJM WHERE ( yt_tran.tornu = jt_ordwk.oorno (+)) AND ( jt_ordwk.prjno = qt_prjm.prjno (+)) AND ( YT_TRAN.TMACO IN ('C3A')) AND ( TO_CHAR(TDATE, 'YYYYMMDD') - 19110000 BETWEEN :as_bgn_date AND :as_end_date) AND ( YT_TRAN.BGCODE IN ('A')) AND ( QT_PRJM.PRODTYPE = JT_PRODTYPE.PRODTYPE) AND ( substr(uf_oorno_tail(yt_tran.tornu), 1, 1) NOT IN ('F'))), 0) AMTA, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM YT_TRAN, JT_ORDWK, QT_PRJM WHERE ( yt_tran.tornu = jt_ordwk.oorno (+)) AND ( jt_ordwk.prjno = qt_prjm.prjno (+)) AND ( YT_TRAN.TMACO IN ('C3A')) AND ( TO_CHAR(TDATE, 'YYYYMMDD') - 19110000 BETWEEN :as_bgn_date AND :as_end_date) AND ( YT_TRAN.BGCODE IN ('F')) AND ( QT_PRJM.PRODTYPE = JT_PRODTYPE.PRODTYPE) AND ( substr(uf_oorno_tail(yt_tran.tornu), 1, 1) NOT IN ('F'))), 0) AMTF, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM YT_TRAN, JT_ORDWK, QT_PRJM WHERE ( yt_tran.tornu = jt_ordwk.oorno (+)) AND ( jt_ordwk.prjno = qt_prjm.prjno (+)) AND ( YT_TRAN.TMACO IN ('C3A')) AND ( TO_CHAR(TDATE, 'YYYYMMDD') - 19110000 BETWEEN :as_bgn_date AND :as_end_date) AND ( YT_TRAN.BGCODE IN ('K')) AND ( QT_PRJM.PRODTYPE = JT_PRODTYPE.PRODTYPE) AND ( substr(uf_oorno_tail(yt_tran.tornu), 1, 1) NOT IN ('F'))), 0) AMTK, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM YT_TRAN, JT_ORDWK, QT_PRJM WHERE ( yt_tran.tornu = jt_ordwk.oorno (+)) AND ( jt_ordwk.prjno = qt_prjm.prjno (+)) AND ( YT_TRAN.TMACO IN ('C3A')) AND ( TO_CHAR(TDATE, 'YYYYMMDD') - 19110000 BETWEEN :as_bgn_date AND :as_end_date) AND ( YT_TRAN.BGCODE IN ('O')) AND ( QT_PRJM.PRODTYPE = JT_PRODTYPE.PRODTYPE) AND ( substr(uf_oorno_tail(yt_tran.tornu), 1, 1) NOT IN ('F'))), 0) AMTO, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM YT_TRAN, JT_ORDWK, QT_PRJM WHERE ( yt_tran.tornu = jt_ordwk.oorno (+)) AND ( jt_ordwk.prjno = qt_prjm.prjno (+)) AND ( YT_TRAN.TMACO IN ('C3A')) AND ( TO_CHAR(TDATE, 'YYYYMMDD') - 19110000 BETWEEN :as_bgn_date AND :as_end_date) AND ( YT_TRAN.BGCODE IN ('D')) AND ( QT_PRJM.PRODTYPE IS NULL AND QT_PRJM.PRODTYPE = JT_PRODTYPE.PRODTYPE) AND ( substr(uf_oorno_tail(yt_tran.tornu), 1, 1) NOT IN ('F'))), 0) AMTD, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM YT_TRAN, JT_ORDWK, QT_PRJM WHERE ( yt_tran.tornu = jt_ordwk.oorno (+)) AND ( jt_ordwk.prjno = qt_prjm.prjno (+)) AND ( YT_TRAN.TMACO IN ('C3A')) AND ( TO_CHAR(TDATE, 'YYYYMMDD') - 19110000 BETWEEN :as_bgn_date AND :as_end_date) AND ( YT_TRAN.BGCODE IN ('Z', 'G', 'A', 'F', 'K', 'O', 'D')) AND ( QT_PRJM.PRODTYPE = JT_PRODTYPE.PRODTYPE) AND ( substr(uf_oorno_tail(yt_tran.tornu), 1, 1) IN ('F'))), 0) AMTS FROM JT_PRODTYPE WHERE PRODTYPE NOT IN ('4') UNION ALL SELECT '' MTYPE, '' PRODTYPE, NVL((SELECT SUM(YT_TRAN.AVGAMT) FROM ~
```

---
## 記錄 ID: 507
* **自然語言提問**: [生產] 查詢納結品項的專案編號批號案別品名銷貨金額材料費人工費製造費及成本差異說明資料
* **判定為不完整的原因**: 括號不匹配 (左括號 7 個，右括號 6 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT JT_CLSITEM.PRJNO, JT_CLSITEM.CSBATNO, JT_CLSITEM.CASECD, PRODNM, SAL_AMT, 0 AS SAL_COST, 0 AS OUT_EXPRESS, NVL(SUM(JT_ORDCLS.EXPENSE_MTRL), 0) AS MFEE, NVL(SUM(JT_ORDCLS.EXPENSE_HMN), 0) AS HFEE, NVL(SUM(JT_ORDCLS.EXPENSE_SHR), 0) AS SFEE, 0 AS MARGIN, 0 AS AVGPRICE, 0 AS AVGPRICE_B, EXPLAIN, EXPLAIN2, '' AS r_prt_date FROM JT_CLSITEM, JT_ORDCLS WHERE (~
```

---
## 記錄 ID: 510
* **自然語言提問**: [人事] 查詢各單位的報工工時統計資料並顯示單位名稱與排序
* **判定為不完整的原因**: 括號不匹配 (左括號 4 個，右括號 3 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT (select trim(dept_name) from TT_DEPT_CODE where dept_code = JT_SRTD.DEPT_CODE) deptcode, (select SEQNO from ct_department where cim2000_code = JT_SRTD.DEPT_CODE) SEQNO, sum(~
```

---
## 記錄 ID: 511
* **自然語言提問**: [人事] 查詢各單位的報工工時統計資料
* **判定為不完整的原因**: 括號不匹配 (左括號 2 個，右括號 1 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT (select name from ct_department where cim2000_code = JT_SRTD.DEPT_CODE) DEPTCODE, to_char(~
```

---
## 記錄 ID: 512
* **自然語言提問**: [人事] 查詢各單位的名稱所屬中心代碼列冊序及相關統計資料
* **判定為不完整的原因**: 括號不匹配 (左括號 4 個，右括號 3 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT (select name from ct_department where cim2000_code = JT_SRTD.DEPT_CODE) deptcode, (select CENTER_CODE from ct_department where cim2000_code = JT_SRTD.DEPT_CODE) CENTER_CODE, (select SEQNO from ct_department where cim2000_code = JT_SRTD.DEPT_CODE) SEQNO, sum(~
```

---
## 記錄 ID: 513
* **自然語言提問**: [人事] 查詢全廠各單位的工時百分比及相關單位資訊
* **判定為不完整的原因**: 括號不匹配 (左括號 5 個，右括號 4 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT (select trim(dept_name) from TT_DEPT_CODE where dept_code = JT_SRTD.DEPT_CODE) deptcode, (select CENTER_CODE from ct_department where cim2000_code = JT_SRTD.DEPT_CODE) CENTER_CODE, (select SEQNO from ct_department where cim2000_code = JT_SRTD.DEPT_CODE) SEQNO, sum(~
```

---
## 記錄 ID: 515
* **自然語言提問**: [人事] 查詢產品及工令進度管制表 for 202 包含訂單號碼 產品分類碼 案別 產品批次號 計畫開始與結束日期 單位名稱及最早計畫開始日期等相關資料
* **判定為不完整的原因**: 括號不匹配 (左括號 3 個，右括號 2 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT ROWNUM, OORNO, PRJNO, SODESC, MITEM, MSTRNO, CASECD, SOCSBDT, SOCSEDT, SOCABDT, SOCAEDT, (SELECT NAME FROM CT_DEPARTMENT WHERE CIM2000_CODE = JT_ORDWK.SODEPT) SODEPT, (SELECT MIN(CSSBDT) FROM JT_PLANMF WHERE PRJNO = ~
```

---
## 記錄 ID: 592
* **自然語言提問**: [人事] 查詢每位員工於指定年度的年資總和
* **判定為不完整的原因**: SQL Guard 阻擋: SQL contains forbidden operation: 'BEGIN'
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select empno, sum(total) total from (select empno, begin, over, aaa, bbb, round(months_between(to_date(bbb,'yyyymmdd'),to_date(aaa,'yyyymmdd'))/12,3) total from (select empno, begin, over, case when to_number(substr(begin,1,4))<:as_year then to_number(:as_year||'0101') else begin end as aaa, case when to_number(substr(over,1,4))>:as_year then to_number(:as_year||'1231') else over end as bbb from (select empno, to_number(TRAN_START)+19110000 begin, to_number(TRAN_END)+19110000 over from ct_emptran) seniority )emptran )total group by empno
```

---
## 記錄 ID: 625
* **自然語言提問**: [通用] 查詢各項採購案件的執行現況明細資料
* **判定為不完整的原因**: 括號不匹配 (左括號 2 個，右括號 1 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT BUDG_CD, pouno, poordno, USERID, psseq, PODEPT1, POREPID2, PODEPT, POABBR, POSTATUS, RECCODE, REGIDT, POAPDT, ovc_pur_dappr_plan, alarm_A, alarm_B, alarm_C, alarm_D, POPVDT1, PODCDT, POCTDT, PRISUDT, prripdt, PRSTAT, POCLDT, POREPID1, POFTVAL2, POATVAL2, CDNM, PSDLVDT, PSPARDT, PORDTE, SUPNAME, MAX(pspvdte), POANS, DISPOSE, PRMYN, PRSYN, ITEMS, POINDT2 FROM (SELECT ~
```

---
## 記錄 ID: 673
* **自然語言提問**: [通用] 查詢指定料號的可用庫存數量
* **判定為不完整的原因**: 括號不匹配 (左括號 22 個，右括號 21 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select round(abssfyqty, 2) + due_inqty - round(yt_cmpmt_due_outqty, 2) - junk - sale sfyqty_y31108 from ( SELECT DISTINCT UF_GET_DUE_INQTY(:as_mitem) AS DUE_INQTY, NVL(UF_GET_DUE_OUTQTY(:as_mitem,'00',''), 0) AS YT_CMPMT_DUE_OUTQTY, (SELECT SUM(A.MLOHQ) FROM VIEW_YT_INVD A WHERE A.MITEM = :as_mitem AND A.IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE GROPUTYPE IN ('1', '2'))) ABSSFYQTY, (SELECT NVL(SUM(IBOHQ), 0) FROM YT_INBG WHERE MITEM = VIEW_YT_INVD.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE GROPUTYPE IN ('1', '2')) AND QUALITY IN ('D', 'E')) JUNK, (SELECT NVL(SUM(IBOHQ), 0) FROM YT_INBG WHERE MITEM = VIEW_YT_INVD.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE GROPUTYPE IN ('1', '2')) AND CLASSIFY IN ('B', 'C', 'D')) SALE FROM ~
```

---
## 記錄 ID: 680
* **自然語言提問**: [通用] 查詢訂單週作業的詳細資料及相關成本與臨時轉撥數量資訊
* **判定為不完整的原因**: 括號不匹配 (左括號 8 個，右括號 6 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT VIEW_JT_ORDWK.OORNO, VIEW_JT_ORDWK.SOYEAR, VIEW_JT_ORDWK.PRJNO, VIEW_JT_ORDWK.MLMTYPE, VIEW_JT_ORDWK.MSTRNO, VIEW_JT_ORDWK.ROSHOPCD, VIEW_JT_ORDWK.CASECD, VIEW_JT_ORDWK.SOBATPR, VIEW_JT_ORDWK.SOBATIM, VIEW_JT_ORDWK.MPRJNO, VIEW_JT_ORDWK.CSDLNO, VIEW_JT_ORDWK.SODESC, VIEW_JT_ORDWK.MITEM, VIEW_JT_ORDWK.MLLREV, VIEW_JT_ORDWK.SOCUTWT, VIEW_JT_ORDWK.SOTCD, VIEW_JT_ORDWK.SODEPT, VIEW_JT_ORDWK.SONDEPT, VIEW_JT_ORDWK.SOCQTRE, VIEW_JT_ORDWK.QTYUNIT, VIEW_JT_ORDWK.SOCQTDL, VIEW_JT_ORDWK.SOCDT, VIEW_JT_ORDWK.SOCSBDT, VIEW_JT_ORDWK.SOCSEDT, VIEW_JT_ORDWK.SOCABDT, VIEW_JT_ORDWK.SOCAEDT, VIEW_JT_ORDWK.SOCFIDT, VIEW_JT_ORDWK.SOCFIWH, VIEW_JT_ORDWK.SOCSTUS, VIEW_JT_ORDWK.ORDCTLCD, VIEW_JT_ORDWK.PRTSTUS_1, VIEW_JT_ORDWK.PRTSTUS, VIEW_JT_ORDWK.SOUPDDT, VIEW_JT_ORDWK.ROSEQNO, VIEW_JT_ORDWK.MAT_REQ, VIEW_JT_ORDWK.PRD_REQ, VIEW_JT_ORDWK.CMPCODE, VIEW_JT_ORDWK.ACCEHS, VIEW_JT_ORDWK.MO_BONUS, VIEW_JT_ORDWK.ORDTYPE, VIEW_JT_ORDWK.SOUPDDSC, VIEW_JT_ORDWK.ORDWKRT, VIEW_JT_ORDWK.SOCINVD, VIEW_JT_ORDWK.SOCEXWH, VIEW_JT_ORDWK.PRTSTUS_2, VIEW_JT_ORDWK.FLOW_CHECK, VIEW_JT_ORDWK.SOURCE_CODE, VIEW_JT_ORDWK.FQTY, VIEW_JT_ORDWK.TOSN, VIEW_JT_ORDWK.UPD_USER, VIEW_JT_ORDWK.SOCFINL, VIEW_JT_ORDWK.SOCQDEL, VIEW_JT_ORDWK.SOCQSCR, VIEW_JT_ORDWK.SOCDAQT, VIEW_JT_ORDWK.SOCNMWH_J, VIEW_JT_ORDWK.SOCSPWH_J, JT_ORDWK.IS_C2D, VIEW_YT_TEMP_TRAN_TORNU_SUM_N.TEMP_C2F FROM VIEW_JT_ORDWK, VIEW_YT_TEMP_TRAN_TORNU_SUM_N, JT_ORDWK WHERE VIEW_JT_ORDWK.MLLREV = VIEW_YT_TEMP_TRAN_TORNU_SUM_N.MLLREV (+) AND VIEW_JT_ORDWK.OORNO = VIEW_YT_TEMP_TRAN_TORNU_SUM_N.TORNU (+) AND trim(VIEW_JT_ORDWK.MITEM) = trim(VIEW_YT_TEMP_TRAN_TORNU_SUM_N.MITEM (+)) AND VIEW_JT_ORDWK.OORNO = JT_ORDWK.OORNO (+) AND (VIEW_JT_ORDWK.OORNO IN (SELECT TORNU FROM VIEW_YT_TEMP_TRAN_TORNU_SUM_N ~
```

---
## 記錄 ID: 683
* **自然語言提問**: [通用] 查詢納結產品工令的工令編號產品組合金額費用年度月份交貨年度專案編號批號案號預算代碼結案數量產品說明倉庫數量部門開工日期品號修訂版條碼及相關費用資料
* **判定為不完整的原因**: 括號不匹配 (左括號 4 個，右括號 1 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT JT_ORDCLS.OORNO, JT_ORDWK.SOCNMWH_J + JT_ORDWK.SOCSPWH_J AS COMP_31, JT_ORDCLS.TTPRICE, JT_ORDCLS.OUT_EXPENSES, JT_ORDCLS.CLSYEAR, JT_ORDCLS.CLSMONTH, JT_ORDCLS.DLVYEAR, JT_ORDCLS.PRJNO, JT_ORDCLS.CSBATNO, JT_ORDCLS.CASECD, JT_ORDCLS.BGCODE, JT_ORDCLS.CLSITEM_QTY, JT_ORDWK.SODESC, JT_ORDWK.SOCNMWH_J, JT_ORDWK.SOCSPWH_J, JT_ORDWK.SODEPT, JT_ORDWK.SOCFIDT, JT_ORDWK.MITEM, JT_ORDWK.MLLREV, '' AS DEL_ITEM, '' AS CHKPRINT, JT_ORDWK.SOCEXWH, JT_ORDCLS.CUORCU, JT_ORDCLS.EXPENSE_MTRL, JT_ORDCLS.EXPENSE_HMN, JT_ORDCLS.EXPENSE_SHR, JT_ORDCLS.EXPENSE_HRS, JT_ORDCLS.OORNO, JT_ORDCLS.MITEM, JT_ORDCLS.MLLREV, BARCODE -- nvl(BARCODE,(SELECT YT_BINPEXT.BARCODE FROM YT_BINPEXT, YT_BINP WHERE YT_BINPEXT.BARCODE = YT_BINP.BARCODE AND YT_BINP.BIBOID IN ('C3Z','C3V') AND YT_BINP.TORNU LIKE JT_ORDCLS.CUORCU || '%' AND YT_BINPEXT.BIRMK LIKE Trim(~
```

---
## 記錄 ID: 684
* **自然語言提問**: [生產] 查詢指定料號現有庫存及相關工令的庫存數量材料費工費攤費工時與採購案號並顯示已納結產出數量
* **判定為不完整的原因**: 括號不匹配 (左括號 36 個，右括號 29 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT '' AS ordctlcd, YT_INBG.MITEM, YT_INBG.MLLREV, YT_INBG.IBCODE, YT_INBG.POORDNO, SUM(YT_INBG.IBOHQ) AS IBOHQ, SUM(YT_INBG.EXPENSE_MTRL) AS EXPENSE_MTRL, SUM(YT_INBG.EXPENSE_HMN) AS EXPENSE_HMN, SUM(YT_INBG.EXPENSE_SHR) AS EXPENSE_SHR, SUM(YT_INBG.EXPENSE_HRS) AS EXPENSE_HRS, 0 AS CLSITEM_QTY, NVL((SELECT SUM(JT_ORDCLS.CLSITEM_QTY) FROM JT_ORDCLS WHERE trim(JT_ORDCLS.OORNO) = trim(YT_INBG.POORDNO)), 0) AS SUM_CLSITEM_QTY FROM YT_INBG WHERE YT_INBG.MITEM = :as_mitem AND YT_INBG.IBCODE = '*' AND YT_INBG.IBOHQ > 0 AND ((SELECT JT_ORDWK.IS_C2D FROM JT_ORDWK WHERE trim(JT_ORDWK.OORNO) = trim(YT_INBG.POORDNO)) <> 'N' OR (LENGTH(RTRIM(YT_INBG.POORDNO)) <= 15)) GROUP BY YT_INBG.MITEM, YT_INBG.MLLREV, YT_INBG.IBCODE, YT_INBG.POORDNO /* HAVING SUM(YT_INBG.IBOHQ) //現有庫存 //當月已納決數量 - NVL( (SELECT SUM(JT_ORDCLS.CLSITEM_QTY) FROM JT_ORDCLS WHERE (trim(OORNO) = trim(YT_INBG.POORDNO) OR (MITEM=YT_INBG.MITEM AND MLLREV = YT_INBG.MLLREV AND BGCODE=YT_INBG.IBCODE)) AND CLSYEAR = :as_year AND CLSMONTH = :as_mon) , 0) //當月已納決產出憑單而且已過帳(已扣除庫存) + NVL( (SELECT SUM(BIQTY) FROM YT_BINPEXT WHERE (BISTAT = 'Y') AND (BARCODE IN (SELECT NVL(BARCODE,(SELECT YT_BINPEXT.BARCODE FROM YT_BINPEXT, YT_BINP WHERE YT_BINPEXT.BARCODE = YT_BINP.BARCODE AND YT_BINP.BIBOID IN ('C3Z','C3V') AND YT_BINP.TORNU LIKE JT_ORDCLS.CUORCU || '%' AND YT_BINPEXT.BIRMK LIKE Trim(~
```

---
## 記錄 ID: 692
* **自然語言提問**: [生產] 查詢各專案各批次各品項的納結品項成本差異說明表包含品名銷售金額納結數量實際成本單價及近三年平均成本單價
* **判定為不完整的原因**: 括號不匹配 (左括號 26 個，右括號 24 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT PRJNO, CSBATNO, CASECD, PRODNM, SAL_AMT, SUM_CLSQTY, SAL_COST, -- round(SAL_COST/SUM_CLSQTY,2) AS AVGPRICE, round(SAL_COST/CLSITEM_QTY,2) AS AVGPRICE, 0 AS MARGIN, 0 AS OUT_EXPRESS, NVL(( SELECT T_SUM/T_QTY FROM (SELECT (NVL(SUM(EXPENSE_SHR), 0)+NVL(SUM(EXPENSE_MTRL), 0)+ NVL(SUM(EXPENSE_HMN), 0)) AS T_SUM ,NVL(SUM(CLSITEM_QTY), 0) AS T_QTY FROM JT_ORDCLS WHERE (PRJNO = A.PRJNO) AND (CLSYEAR NOT IN (A.CLSYEAR)) AND (CLSYEAR >= A.CLSYEAR - 3)) WHERE T_QTY > 0 ),0) AS AVGPRICE_B, '' AS EXPLAIN, '' AS EXPLAIN2, '' AS r_prt_date FROM( SELECT JT_CLSITEM.CLSYEAR, JT_CLSITEM.CLSMONTH, JT_CLSITEM.PRJNO, JT_CLSITEM.CSBATNO, JT_CLSITEM.CASECD, JT_CLSITEM.CLSITEM_QTY, PRODNM, SAL_AMT, SUM_CLSQTY, NVL(SUM(JT_ORDCLS.EXPENSE_MTRL), 0)+NVL(SUM(JT_ORDCLS.EXPENSE_HMN), 0)+ NVL(SUM(JT_ORDCLS.EXPENSE_SHR), 0) AS SAL_COST FROM JT_CLSITEM, JT_ORDCLS WHERE (~
```

---
## 記錄 ID: 776
* **自然語言提問**: [人事] 查詢指定年度月份每位員工依職稱在該期間內的異動天數總計
* **判定為不完整的原因**: SQL Guard 阻擋: SQL contains forbidden operation: 'BEGIN'
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select empno, vocat, sum(total) total from (select empno, vocat, begin, over, aaa, bbb, to_date(bbb,'yyyymmdd') - to_date(aaa,'yyyymmdd')+1 total from (select empno, vocat, begin, over, case when to_number(substr(begin,1,6))<:as_year||:as_month then to_number(:as_year||:as_month||'01') else begin end as aaa, case when to_number(substr(over,1,4))>=:as_year and to_number(substr(over,5,2))>:as_month then to_number(:as_year||:as_month||to_char(LAST_DAY(to_date(:as_year||:as_month,'yyyymm')),'dd')) else over end as bbb from (select empno, vocat, to_number(TRAN_START)+19110000 begin, to_number(TRAN_END)+19110000 over from ct_emptran) seniority )emptran WHERE to_number(substr(begin,1,6)) <= :as_year||:as_month and to_number(substr(over,1,6)) >= :as_year||:as_month )total group by empno,vocat
```

---
## 記錄 ID: 780
* **自然語言提問**: [人事] 查詢每位人員的廠發激勵金總金額
* **判定為不完整的原因**: 括號不匹配 (左括號 3 個，右括號 1 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT sldno, SUM(AMOUNT) amount FROM CT_BNREWARD WHERE ( to_char (~
```

---
## 記錄 ID: 813
* **自然語言提問**: [品保] 查詢各專案對應的料號型態號中文品名另件號圖號及規格描述資料
* **判定為不完整的原因**: 括號不匹配 (左括號 3 個，右括號 1 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select qt_prjm.prjno ,qt_itmd.mitem , qt_itmd.mllrev ,mpcdsc ,mstrno , mlbpno , mmspec from qt_itmd ,qt_prjm WHERE (qt_itmd.tvkey =qt_prjm.tvkey ) and ( ( ~
```

---
## 記錄 ID: 868
* **自然語言提問**: [通用] 查詢指定資產編號的資訊資產明細資料
* **判定為不完整的原因**: SQL Guard 阻擋: Security check: detected forbidden keyword 'REPLACE' (word-boundary)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select trim(ea_cs_equipment.csno) csno, trim(ea_cs_equipment.rmno) rmno, trim(ea_cs_equipment.mndno) mndno, trim(ea_cs_equipment.etype) etype, trim(ea_cs_equipment.cname) cname, trim(ea_cs_equipment.os) os, trim(ea_cs_equipment.ram) ram, trim(ea_cs_equipment.hd) hd, trim(ea_cs_equipment.cdrom) cdrom, trim(ea_cs_equipment.scanner) scanner, trim(ea_cs_equipment.hostname) hostname, trim(ea_cs_equipment.ipv4) ipv4, trim(ea_cs_equipment.mac) mac, trim(ea_cs_equipment.deptno) deptno, trim(ea_cs_equipment.keeper) keeper, trim(ea_cs_equipment.location) location, --replace(replace(trim(ea_cs_equipment.memo),chr(13),''),chr(10),'') memo, trim(ea_cs_equipment.memo) memo, ea_cs_equipment.uplastcheck, ea_cs_equipment.feedback_dt, trim(ea_cs_equipment.kerberos) kerberos, trim(ea_cs_equipment.prtsecure) prtsecure, trim(ea_cs_equipment.state) state, trim(ea_cs_equipment.cpu) cpu, trim(ea_cs_equipment.deptname) deptname, trim(ea_cs_equipment.fortno) fortno, trim(ea_cs_equipment.officescan_ver) officescan_ver, trim(ea_cs_equipment.info_ver) info_ver, trim(ea_cs_equipment.account_ctrl) account_ctrl, fageltd, fasprice, secret, importance, assets, used, is_remind, entry_date, '' entry_date_ctrl , factory_code, trim(model) model, scrap_date --報廢日期(民國) from ea_cs_equipment where trim(csno)=:as_csno
```

---
## 記錄 ID: 894
* **自然語言提問**: [通用] 查詢各項採購案件的執行現況明細資料
* **判定為不完整的原因**: 括號不匹配 (左括號 2 個，右括號 1 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT BUDG_CD, poordno, USERID, psseq, PODEPT1, PODEPT, POABBR, POSTATUS, RECCODE, REGIDT, POAPDT, ovc_pur_dappr_plan, alarm_A, alarm_B, alarm_C, alarm_D, POPVDT1, PODCDT, POCTDT, PRISUDT, prripdt, PRSTAT, POCLDT, POREPID1, POFTVAL2, POATVAL2, CDNM, PSDLVDT, PSPARDT, PORDTE, SUPNAME, MAX(pspvdte), POANS, DISPOSE, PRMYN, PRSYN, ITEMS FROM (SELECT ~
```

---
## 記錄 ID: 896
* **自然語言提問**: [通用] 查詢各類型財務勞務工程依金額區間分級的筆數與金額統計資料並區分是否有指定日期
* **判定為不完整的原因**: 括號不匹配 (左括號 20 個，右括號 19 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select podef, degree, degrees, sum(cnt_0) as cnt_0, sum(sum_0) as sum_0, sum(cnt_a1) as cnt_a1, sum(sum_b1) as sum_b1, sum(cnt_a2) as cnt_a2, sum(sum_b2) as sum_b2 from( SELECT case when (nvl(poftval2,0) > 50000000 and podef = 'A') OR (nvl(poftval2,0) > 10000000 and podef = 'B') then 1 else case when (nvl(poftval2,0) > 20000000 and podef = 'A') then 2 else 3 end end degree, case when podef = 'A' THEN '財務' ELSE case when podef = 'B' THEN '勞務' ELSE '工程' end end degrees, 1 as cnt_0, podef, nvl(poftval2,0) as sum_0, decode(popvdt1,null,0,1) as cnt_a1, decode(popvdt1,null,0,nvl(poftval2,0)) as sum_b1, decode(popvdt1,null,1,0) as cnt_a2, decode(popvdt1,null,nvl(poftval2,0),0) as sum_b2 FROM ~
```

---
## 記錄 ID: 898
* **自然語言提問**: [通用] 查詢廠商的基本資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select * from (SELECT ~
```

---
## 記錄 ID: 902
* **自然語言提問**: [人事] 查詢單位代碼對應的單位名稱
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT (SELECT DEPT_NAME FROM TT_DEPT_CODE WHERE DEPT_CODE = A.~
```

---
## 記錄 ID: 966
* **自然語言提問**: [生產] 查詢產品代碼重大案件屬性的相關維護資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT B.ORDSTATUS, B.COYEAR, A.MYEAR, B.CUCUOR, B.CLLNMN, B.PRJNO, A.PRJNO, B.PRODNM, B.MITEM, B.MPCDSC, B.CLQTOR, B.MUTMS, B.CLEPRC, A.MAJOR FROM JT_MAJORPRJNO A, (SELECT DISTINCT ~
```

---
## 記錄 ID: 1004
* **自然語言提問**: [通用] 查詢銷令工令的領料記錄明細資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT CASE WHEN INRT1.ITOITEM IS NULL AND INRT2.IRNITEM IS NULL THEN A.MITEM ELSE CASE WHEN INRT1.ITOITEM IS NULL THEN INRT2.IRNITEM ELSE INRT1.ITOITEM END END MITEM, A.MLLREV, CASE WHEN INRT2.IRNITEM IS NOT NULL THEN INRT2.ITOITEM ELSE A.MITEM END MITEM1, CASE WHEN INRT2.IRNITEM IS NOT NULL THEN INRT2.IRNITEM END MITEM2, A.MPCDSC, A.MLBIN, A.ADMQTY, A.TMACO, A.TQUAN, A.TDATE FROM (SELECT ~
```

---
## 記錄 ID: 1006
* **自然語言提問**: [生產] 查詢各工令各道次歷年下令工時及相關工令資訊分析表
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT JT_ORDWK.OORNO, JT_ORDWK.SOYEAR, JT_ORDWK.PRJNO, JT_ORDWK.MSTRNO, JT_ORDWK.ROSHOPCD, JT_ORDWK.CASECD, JT_ORDWK.SOBATPR, JT_ORDWK.SOBATIM, JT_ORDWK.SODESC, JT_ORDWK.MITEM, JT_ORDWK.SODEPT, JT_ORDWK.SOCQTRE, JT_ORDWK.SOCDT, JT_ORDWK.SOCSTUS, JT_ORDWK.SOCEXWH, JT_ORDWK.SOCNMWH_J, JT_ORDWK.SOCSPWH_J, JT_ORDWK.SOCDAQT, JT_ORDWK.SOCFIWH, '' PROPORTION, ' ' as compute_row, '' as r_prt_date FROM JT_ORDWK WHERE (~
```

---
## 記錄 ID: 1007
* **自然語言提問**: [生產] 查詢第202廠的納結品項成本差異統計資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT '202' AS FACTORYNO, '第202廠' AS FACTORYNAME, 0 AS AMOUNT, 0 AS SAL_AMT, 0 AS SAL_COST, 0 AS OUT_EXPRESS, 0 AS MFEE, 0 AS HFEE, 0 AS SFEE, 0 AS MARGIN, 0 AS AVGPRICE, '' AS r_prt_date FROM JT_CLSITEM WHERE (~
```

---
## 記錄 ID: 1008
* **自然語言提問**: [生產] 查詢第202廠會計月報與製造部門帳務差異分析資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT '202' AS FACTORYNO, '第202廠' AS FACTORYNAME, 0 AS SAL_AMT_FJ, 0 AS SAL_COST_FJ, 0 AS MATERIALS_FJ, 0 AS SUPPLIES_FJ, 0 AS SAL_AMT, 0 AS SAL_COST, 0 AS OUT_EXPRESS, 0 AS MFEE, 0 AS HFEE, 0 AS SFEE, 0 AS MATERIALS, 0 AS SUPPLIES, 0 AS FK_410203, 0 AS FK_510203, 0 AS FK_110402, 0 AS FK_110403, '' AS REMARK, '' AS r_prt_date FROM JT_CLSITEM WHERE (~
```

---
## 記錄 ID: 1009
* **自然語言提問**: [生產] 查詢第202廠的納結產品工令耗料差異統計資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT '202' AS FACTORYNO, '第202廠' AS FACTORYNAME, 0 AS NUMBER1, 0 AS NUMBER2, 0 AS NUMBER3, 0 AS NUMBER4, 0 AS NUMBER5, 0 AS NUMBER6, '' AS r_prt_date FROM JT_CLSITEM WHERE (~
```

---
## 記錄 ID: 1033
* **自然語言提問**: [生產] 查詢指定年度月份符合單位條件及員工條件且已申之火工獎金維護主檔資料並顯示相關火工作業內容及獎金核發狀態
* **判定為不完整的原因**: SQL Guard 阻擋: Security check: detected forbidden keyword 'REPLACE' (word-boundary)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select distinct bns.year ,bns.month ,bns.deptno ,bns.dept_name ,bns.rnkno ,bns.rank ,bns.empno ,bns.name ,bns.hazard_rating --危險等級 ,bns.firework_duty --火工作業內容 ,replace(replace(replace(bns.firework_desc,chr(9),''),chr(10),''),chr(13),'') firework_desc --工作說明 ,bns.workprocedure --工作程序及風險等級 ,bns.firework_date --火工作業日期 ,bns.oorno_days --工令作業天數 ,bns.days_sum --火工作業天數合計 ,bns.approved_amount --核發金額 ,bns.manager_lice_no --火工作業主管証照代碼 ,bns.manager_lice_name --火工作業主管証照名稱 ,bns.manager_serial --火工作業主管証照証號 ,bns.manager_getdate --火工作業主管証照獲取日期 ,bns.manager_enddate --火工作業主管証照有效期限 ,bns.manager_status --火工作業主管証照有效狀態 ,bns.person_lice_no --個人火工簽証代碼 ,bns.person_lice_name --個人火工簽証名稱 ,bns.person_serial --個人火工簽証証號 ,bns.person_getdate --個人火工簽証獲取日期 ,bns.person_enddate --個人火工簽証有效期限 ,bns.person_status --個人火工簽証有效狀態 ,bns.oorno --工令號 ,bns.prjno --工令代碼 ,bns.license_no --報工之火工作業道次 ,bns.license_name --報工之火工作業道次名稱 ,bns. socfidt --完工日期 ,bns. sel --申請狀態 ,bns.upd_date ,bns.upd_user ,(case when hazard_rating='1' and sel='Y' then 'Y' else 'N' end) sel_1 ,(case when hazard_rating='2' and sel='Y' then 'Y' else 'N' end) sel_2 ,(case when hazard_rating='3' and sel='Y' then 'Y' else 'N' end) sel_3 ,nvl(mark.mark,'N') mark --結算狀態 ,0 amount_1 ,0 amount_2 ,0 amount_3 ,0 days_1 ,0 days_2 ,0 days_3 ,emp.deptno now_emp_deptno from JT_FIREWORK_BONUS bns ,jt_firework_bonus_mark mark ,ct_employ emp where bns.year=mark.year(+) and bns.month=mark.month(+) and emp.deptno=mark.deptno(+) and bns.empno=emp.empno and bns.year=to_number(:as_year) and bns.month=to_number(:as_month) and (emp.deptno like :as_deptno or bns.deptno like :as_deptno) and (bns.empno like :as_empno or bns.name like :as_empno) and bns.sel='Y'
```

---
## 記錄 ID: 1154
* **自然語言提問**: [通用] 查詢年度各產品造別分月份的解繳計劃統計總表
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT A.CASECD, t_count, amount_p, prpm1, prpm2, prpm3, prpm4, prpm5, prpm6, prpm7, prpm8, prpm9, prpm10, prpm11, prpm12, pram1, pram2, pram3, pram4, pram5, pram6, pram7, pram8, pram9, pram10, pram11, pram12, ach_p1, ach_p2, ach_p3, ach_p4, ach_p5, ach_p6, ach_p7, ach_p8, ach_p9, ach_p10, ach_p11, ach_p12, comp_01 FROM ( SELECT ~
```

---
## 記錄 ID: 1155
* **自然語言提問**: [通用] 查詢各委製軍種年度分月解繳計劃統計資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT A.CUCUTY, t_count, amount_p, prpm1, prpm2, prpm3, prpm4, prpm5, prpm6, prpm7, prpm8, prpm9, prpm10, prpm11, prpm12, pram1, pram2, pram3, pram4, pram5, pram6, pram7, pram8, pram9, pram10, pram11, pram12, ach_p1, ach_p2, ach_p3, ach_p4, ach_p5, ach_p6, ach_p7, ach_p8, ach_p9, ach_p10, ach_p11, ach_p12, comp_01 FROM ( SELECT ~
```

---
## 記錄 ID: 1156
* **自然語言提問**: [通用] 查詢年度各產品類別分月份的解繳計劃統計資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT A.PRJ_CLS, t_count, amount_p, prpm1, prpm2, prpm3, prpm4, prpm5, prpm6, prpm7, prpm8, prpm9, prpm10, prpm11, prpm12, pram1, pram2, pram3, pram4, pram5, pram6, pram7, pram8, pram9, pram10, pram11, pram12, ach_p1, ach_p2, ach_p3, ach_p4, ach_p5, ach_p6, ach_p7, ach_p8, ach_p9, ach_p10, ach_p11, ach_p12, comp_01 FROM ( SELECT ~
```

---
## 記錄 ID: 1157
* **自然語言提問**: [通用] 查詢各年度分月份的委製款解繳計劃統計資料
* **判定為不完整的原因**: 括號不匹配 (左括號 1 個，右括號 0 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT A.CO_YEAR, t_count, amount_p, prpm1, prpm2, prpm3, prpm4, prpm5, prpm6, prpm7, prpm8, prpm9, prpm10, prpm11, prpm12, pram1, pram2, pram3, pram4, pram5, pram6, pram7, pram8, pram9, pram10, pram11, pram12, ach_p1, ach_p2, ach_p3, ach_p4, ach_p5, ach_p6, ach_p7, ach_p8, ach_p9, ach_p10, ach_p11, ach_p12, comp_01 FROM ( SELECT ~
```

---
## 記錄 ID: 1243
* **自然語言提問**: [通用] 查詢所有資訊資產的詳細資料列表
* **判定為不完整的原因**: SQL Guard 阻擋: Security check: detected forbidden keyword 'REPLACE' (word-boundary)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
select trim(ea_cs_equipment.csno) csno, trim(ea_cs_equipment.cname) cname, trim(ea_cs_equipment.location) location, trim(ea_cs_equipment.keeper) keeper, trim(ea_cs_equipment.deptname) deptname, ea_cs_equipment.entry_date, ea_cs_equipment.model, rmno, mndno, etype, os, ram, hd, cdrom, scanner, hostname, ipv4, mac, deptno, replace(replace(trim(ea_cs_equipment.memo),chr(13),' '),chr(10),' ') memo, uplastcheck, feedback_dt, kerberos, prtsecure, state, cpu, fortno, officescan_ver, info_ver, account_ctrl, fageltd, fasprice, secret, importance, assets, used, is_remind, ipv4_2, filesecure, mac_2, factory_code, is_filechange, scrap_date from ea_cs_equipment order by to_number(case when instr(csno,'-') >0 then substr(csno,1,instr(csno,'-') - 1) else csno end) desc,csno
```

---
## 記錄 ID: 1309
* **自然語言提問**: [品保] 查詢指定年度各料號的中文品名年度平均庫存金額各年度入庫出庫數量現有庫存量及相關採購專案資訊
* **判定為不完整的原因**: 括號不匹配 (左括號 36 個，右括號 35 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT YT_MATERIAL.YEAR, E.MITEM MITEM, (SELECT MPCDSC FROM QT_ITMD WHERE MITEM = E.MITEM AND MLLREV IN ('00')) MPCDSC, NVL(SUM(E.AVGAMT), 0) AVGAMT, NVL(SUM(E.Y0C2), 0) IN0, NVL(SUM(E.Y0C3), 0) OUT0, NVL(SUM(E.Y1C2), 0) IN1, NVL(SUM(E.Y1C3), 0) OUT1, NVL(SUM(E.Y2C2), 0) IN2, NVL(SUM(E.Y2C3), 0) OUT2, NVL((SELECT SUM(MLOHQ) FROM YT_INVD WHERE MITEM = E.MITEM), 0) MLOHQ, YT_MATERIAL.CAUSENO, YT_MATERIAL.REMARK, UF_GET_TRAN_TORNU(:as_year, E.MITEM) POORDNO, YT_MATERIAL.PODEPT, YT_MATERIAL.USERID, (SELECT PURYEAR_BEG FROM YT_INBG WHERE MITEM = E.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE IS_PRODUCE IN ('Y')) AND ROWNUM = 1) PURYEAR_BEG, (SELECT PURYEAR_END FROM YT_INBG WHERE MITEM = E.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE IS_PRODUCE IN ('Y')) AND ROWNUM = 1) PURYEAR_END, (SELECT PURPRJNO FROM YT_INBG WHERE MITEM = E.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE IS_PRODUCE IN ('Y')) AND ROWNUM = 1) PURPRJNO, (SELECT PURPOORDNO FROM YT_INBG WHERE MITEM = E.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE IS_PRODUCE IN ('Y')) AND ROWNUM = 1) PURPOORDNO, YT_MATERIAL.RECCODE FROM (SELECT A.MITEM, A.MLLREV, B.MPCDSC, SUM(CASE WHEN (A.TMACO = 'C2A' OR A.TMACO = 'C2V') AND A.YEAR = :as_year THEN A.AVGAMT ELSE 0 END) - SUM(CASE WHEN A.TMACO = 'C3V' AND A.YEAR = :as_year THEN A.AVGAMT ELSE 0 END) ~
```

---
## 記錄 ID: 1310
* **自然語言提問**: [品保] 查詢指定年度各料號的中文品名各年度領用與耗用數量現有庫存量及相關採購專案資訊
* **判定為不完整的原因**: 括號不匹配 (左括號 34 個，右括號 33 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT E.MITEM MITEM, (SELECT MPCDSC FROM QT_ITMD WHERE MITEM = E.MITEM AND MLLREV IN ('00')) MPCDSC, NVL(SUM(E.Y0C2), 0) IN0, NVL(SUM(E.Y0C3), 0) OUT0, NVL(SUM(E.Y1C2), 0) IN1, NVL(SUM(E.Y1C3), 0) OUT1, NVL(SUM(E.Y2C2), 0) IN2, NVL(SUM(E.Y2C3), 0) OUT2, NVL((SELECT SUM(MLOHQ) FROM YT_INVD WHERE MITEM = E.MITEM), 0) MLOHQ, UF_GET_TRAN_TORNU(:as_year, E.MITEM) POORDNO, (SELECT PURYEAR_BEG FROM YT_INBG WHERE MITEM = E.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE IS_PRODUCE IN ('Y')) AND ROWNUM = 1) PURYEAR_BEG, (SELECT PURYEAR_END FROM YT_INBG WHERE MITEM = E.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE IS_PRODUCE IN ('Y')) AND ROWNUM = 1) PURYEAR_END, (SELECT PURPRJNO FROM YT_INBG WHERE MITEM = E.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE IS_PRODUCE IN ('Y')) AND ROWNUM = 1) PURPRJNO, (SELECT PURPOORDNO FROM YT_INBG WHERE MITEM = E.MITEM AND IBCODE IN (SELECT BGCODE FROM YT_BG_CODETBL WHERE IS_PRODUCE IN ('Y')) AND ROWNUM = 1) PURPOORDNO FROM (SELECT A.MITEM, A.MLLREV, B.MPCDSC, SUM(CASE WHEN (A.TMACO = 'C2A' OR A.TMACO = 'C2V') AND A.YEAR = :as_year THEN A.TQUAN ELSE 0 END) - SUM(CASE WHEN A.TMACO = 'C3V' AND A.YEAR = :as_year THEN A.TQUAN ELSE 0 END) ~
```

---
## 記錄 ID: 1328
* **自然語言提問**: [採購] 查詢間接材料耗用的明細資料依經費別與基金類別分組並顯示各項目之單號日期品項名稱部門數量單價金額及相關科目資訊
* **判定為不完整的原因**: 括號不匹配 (左括號 10 個，右括號 6 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT yt_tran.tornu , yt_tran.mutms , yt_tran.tdate , yt_tran.mitem , yt_tran.mllrev , yt_tran.trdept , yt_tran.tquan , yt_tran.avgprice , yt_tran.avgamt , yt_tran.bidept , qt_itmd.mpcdsc , yt_tran.expcd , yt_tran.baseact FROM yt_tran , qt_itmd WHERE (yt_tran.mitem = qt_itmd.mitem(+)) AND ( yt_tran.mllrev = qt_itmd.mllrev (+)) AND ( YT_TRAN.TMACO IN ('C3A','C3L')) AND (( length(RTRIM(~
```

---
## 記錄 ID: 1329
* **自然語言提問**: [採購] 查詢間接材料耗用明細依經費別分組的相關資料
* **判定為不完整的原因**: 括號不匹配 (左括號 9 個，右括號 6 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT yt_tran.tornu , yt_tran.mutms , yt_tran.tdate , yt_tran.mitem , yt_tran.mllrev , yt_tran.trdept , yt_tran.tquan , yt_tran.avgprice , yt_tran.avgamt , yt_tran.bidept , qt_itmd.mpcdsc , yt_tran.expcd , yt_tran.baseact FROM yt_tran , qt_itmd WHERE (yt_tran.mitem = qt_itmd.mitem(+)) AND ( yt_tran.mllrev = qt_itmd.mllrev (+)) AND ( YT_TRAN.TMACO IN ('C3A','C3L')) AND ( length(RTRIM(~
```

---
## 記錄 ID: 1330
* **自然語言提問**: [品保] 查詢間接材料耗用統計依經費別及基金類別並顯示單號料號部門耗用數量平均金額中文品名經費代碼基金代碼及基礎活動
* **判定為不完整的原因**: 括號不匹配 (左括號 11 個，右括號 7 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT yt_tran.tornu , yt_tran.mitem , yt_tran.trdept , yt_tran.tquan , yt_tran.avgamt , qt_itmd.mpcdsc , yt_tran.expcd , dt_divi_dept.divi_cd , yt_tran.baseact FROM qt_itmd , yt_tran , dt_divi_dept WHERE ( yt_tran.mitem = qt_itmd.mitem (+)) AND ( yt_tran.mllrev = qt_itmd.mllrev (+)) AND ( yt_tran.trdept = dt_divi_dept.dept_code ) AND ( YT_TRAN.TMACO IN ('C3A','C3L')) AND (( length(RTRIM(~
```

---
## 記錄 ID: 1331
* **自然語言提問**: [品保] 查詢間接材料耗用統計依經費別分組顯示各料號在指定部門的耗用數量平均金額及相關品名與經費資訊
* **判定為不完整的原因**: 括號不匹配 (左括號 8 個，右括號 5 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT yt_tran.tornu , yt_tran.mitem , yt_tran.trdept , yt_tran.tquan , yt_tran.avgamt , qt_itmd.mpcdsc , yt_tran.expcd , dt_divi_dept.divi_cd , yt_tran.baseact FROM qt_itmd , yt_tran , dt_divi_dept WHERE ( yt_tran.mitem = qt_itmd.mitem ) AND ( yt_tran.mllrev = qt_itmd.mllrev ) AND ( yt_tran.trdept = dt_divi_dept.dept_code ) AND ( YT_TRAN.TMACO IN ('C3A','C3L')) AND ( length(RTRIM(~
```

---
## 記錄 ID: 1332
* **自然語言提問**: [採購] 查詢間接材料餘料退庫的明細資料依經費別和基金類別分組顯示
* **判定為不完整的原因**: 括號不匹配 (左括號 8 個，右括號 5 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT yt_tran.tornu , yt_tran.mutms , yt_tran.tdate , yt_tran.mitem , yt_tran.mllrev, yt_tran.trdept , yt_tran.tquan , yt_tran.avgprice , yt_tran.avgamt , yt_tran.bidept , qt_itmd.mpcdsc , yt_tran.expcd , substr(tornu,1,4) as prjcode, yt_tran.baseact, yt_tran.code FROM yt_tran, qt_itmd WHERE (yt_tran.mitem = qt_itmd.mitem) AND (yt_tran.mllrev = qt_itmd.mllrev) AND ( YT_TRAN.TMACO IN ('C2K')) AND ( length(RTRIM(~
```

---
## 記錄 ID: 1333
* **自然語言提問**: [採購] 查詢間接材料餘料退庫的明細資料包含退庫單號退庫類型退庫日期品項品項說明經費別退庫部門退庫數量平均單價平均金額投標部門專案代碼及基本活動並依據指定的條件篩選
* **判定為不完整的原因**: 括號不匹配 (左括號 9 個，右括號 5 個)
* **原始錯誤訊息**: Manually marked as NOT OK from public.nl2sql_training_example1
* **完整失敗 SQL 語法**:
```sql
SELECT yt_tran.tornu , yt_tran.mutms , yt_tran.tdate , yt_tran.mitem , yt_tran.mllrev , yt_tran.trdept , yt_tran.tquan , yt_tran.avgprice , yt_tran.avgamt , yt_tran.bidept , qt_itmd.mpcdsc , yt_tran.expcd , substr(tornu, 1, 4) as prjcode, yt_tran.baseact FROM yt_tran, qt_itmd WHERE (yt_tran.mitem = qt_itmd.mitem) AND (yt_tran.mllrev = qt_itmd.mllrev) AND ( YT_TRAN.TMACO IN ('C2M','C2K') ) AND ((length(RTRIM(~
```

---