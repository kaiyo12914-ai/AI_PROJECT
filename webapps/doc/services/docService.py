from __future__ import annotations

from typing import Any, Dict, Sequence

from webapps.doc.services.doc_db_router import DocDBTarget, resolve_doc_db_target


class docService:
    """
    DOC service layer for document/incoming/attachment APIs.
    Supports plant-based DB routing:
    - MPC/202 -> Sybase (mnda.dbo)
    - 205/209/401 -> Oracle (MNDQ/MNDV/MNDI)
    
    ✅ Oracle 特性優化：針對 CHAR 型態欄位全面使用 TRIM() 消除空白字串。
    """

    def __init__(
        self,
        *,
        plant: str = "",
        login_user_name: str = "",
        login_user_id: str = "",
        db_target: DocDBTarget | None = None,
    ):
        from webapps.doc.repositories.docRepository import docRepository

        self.repo = docRepository()
        self.target = db_target or resolve_doc_db_target(
            plant=plant,
            user_name=login_user_name,
            user_id=login_user_id,
        )
        self.db_type = self.target.db_type
        self.db_profile = self.target.db_profile
        self.owner = self.target.owner

    # Sybase todo list SQL (metadata reference / debug use)
    SYB_INCOMING_TODO_LIST_SQL = (
        "SELECT TOP 60 "
        "COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS IM_GRSNO, "
        "COALESCE(IM.IM_PSID, EM.EM_PSID) AS IM_PSID, "
        "CONVERT(VARBINARY(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS TD_SUBJ, "
        "EF.EF_ID AS EF_ID, "
        "CONVERT(VARBINARY(4000), EF.EF_NAME) AS EF_NAME, "
        "EF.EF_PAGE "
        "FROM {em} EM "
        "LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO "
        "LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID "
        "WHERE (CONVERT(VARCHAR(64), IM.IM_PSID) = ? OR CONVERT(VARCHAR(64), EM.EM_PSID) = ?) "
        "AND IM.IM_CNCDT IS NULL "
        "ORDER BY EF.EF_PAGE"
    )

    @property
    def is_oracle(self) -> bool:
        return self.db_type == "oracle"

    def _tbl(self, table: str) -> str:
        owner = str(self.owner or "").strip()
        if not owner:
            return table
        return f"{owner}.{table}"

    def _query_all(self, sql: str, params: list | dict | None = None):
        return self.repo.query_all(
            sql,
            params=params,
            db_type=self.db_type,
            db_profile=self.db_profile,
        )

    def _query_one(self, sql: str, params: list | dict | None = None):
        return self.repo.query_one(
            sql,
            params=params,
            db_type=self.db_type,
            db_profile=self.db_profile,
        )

    @staticmethod
    def _safe_limit(limit: int, default: int = 200, max_limit: int = 20000) -> int:
        try:
            n = int(limit)
        except Exception:
            n = default
        return min(max(n, 1), max_limit)

    @staticmethod
    def _like_value(s: str) -> str:
        raw = (s or "").strip()
        escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @staticmethod
    def _normalize_psids(psids: Sequence[str] | None) -> list[str]:
        out: list[str] = []
        seen = set()
        for p in (psids or []):
            v = str(p or "").strip()
            if not v or v in seen:
                continue
            seen.add(v)
            out.append(v)
        return out

    @staticmethod
    def _oracle_in_clause_params(prefix: str, values: Sequence[str]) -> tuple[str, dict[str, str]]:
        params: dict[str, str] = {}
        binds: list[str] = []
        for i, raw in enumerate(values):
            key = f"{prefix}{i}"
            params[key] = str(raw or "").strip()
            binds.append(f":{key}")
        return ",".join(binds), params

    def query_import_from_template(self, grsno: str):
        tm = self._tbl("DCS3_TRST_MST")
        td = self._tbl("DCS3_TRST_DAT")
        df = self._tbl("DCS0_DOC_FILE")
        if self.is_oracle:
            sql = f"""
            SELECT
                TRIM(TM.TM_GRSNO) AS TM_GRSNO,
                TRIM(TM.TM_RSTP) AS TM_RSTP,
                TRIM(TD.TD_FORMAT) AS TD_FORMAT,
                TRIM(TD.TD_SUBJ) AS TD_SUBJ,
                TM.TM_DATE AS TM_DATE,
                TRIM(TM.TM_PSID) AS TM_PSID,
                TRIM(TM.TM_NAME) AS TM_NAME,
                TRIM(TD.TD_PATH) AS TD_PATH,
                TRIM(DF.DF_NAME) AS DF_NAME,
                DF.DF_DATA AS DF_DATA,
                NVL(DBMS_LOB.GETLENGTH(DF.DF_DATA), 0) AS DF_DATA_LEN
            FROM {tm} TM
            LEFT JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO
            LEFT JOIN {df} DF ON TRIM(DF.DF_PATH) = TRIM(TD.TD_PATH)
            WHERE TRIM(TM.TM_GRSNO) = :grsno
              AND TM.TM_DATE = (
                  SELECT MAX(DT.TM_DATE)
                  FROM {tm} DT
                  WHERE TRIM(DT.TM_GRSNO) = TRIM(TM.TM_GRSNO)
              )
            ORDER BY TD.TD_FORMAT
            """
            return self._query_all(sql, {"grsno": str(grsno or "").strip()})

        # Sybase branch
        sql = f"""
        SELECT
            TM.TM_GRSNO AS TM_GRSNO,
            CONVERT(VARBINARY(400), TM.TM_RSTP) AS TM_RSTP,
            CONVERT(VARBINARY(400), TD.TD_FORMAT) AS TD_FORMAT,
            CONVERT(VARBINARY(4000), TD.TD_SUBJ) AS TD_SUBJ,
            TM.TM_DATE AS TM_DATE,
            TM.TM_PSID AS TM_PSID,
            CONVERT(VARBINARY(400), TM.TM_NAME) AS TM_NAME,
            TD.TD_PATH AS TD_PATH,
            CONVERT(VARBINARY(400), DF.DF_NAME) AS DF_NAME,
            DF.DF_DATA AS DF_DATA,
            DATALENGTH(DF.DF_DATA) AS DF_DATA_LEN
        FROM {tm} TM
        LEFT JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO
        LEFT JOIN {df} DF ON DF.DF_PATH = TD.TD_PATH
        WHERE TM.TM_GRSNO = ?
          AND TM.TM_DATE = (
              SELECT MAX(TM_DATE)
              FROM {tm} DT
              WHERE DT.TM_GRSNO = TM.TM_GRSNO
          )
        ORDER BY TD.TD_FORMAT
        """
        return self._query_all(sql, [grsno])

    def lookup_incoming(self, login_user: str, tm_grsno: str):
        em = self._tbl("DCS1_EMAL_TMP")
        im = self._tbl("DCS1_IN_MAST")
        ef = self._tbl("DCS1_EMAL_FILE")

        if self.is_oracle:
            sql = f"""
            SELECT * FROM (
                SELECT
                    TRIM(COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) AS IM_GRSNO,
                    TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) AS IM_PSID,
                    TRIM(COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS TD_SUBJ,
                    TRIM(EF.EF_ID) AS EF_ID,
                    TRIM(EF.EF_NAME) AS EF_NAME,
                    TRIM(EF.EF_PAGE) AS EF_PAGE
                FROM {em} EM
                LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO
                LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID
                WHERE (TRIM(IM.IM_PSID) = :login_user OR TRIM(EM.EM_PSID) = :login_user)
                  AND TRIM(EM.EM_GRSNO) = :grsno
                ORDER BY EF.EF_PAGE
            )
            WHERE ROWNUM <= 60
            """
            return self._query_all(sql, {"login_user": str(login_user).strip(), "grsno": str(tm_grsno).strip()})

        # Sybase branch
        sql = f"""
        SELECT TOP 60
            COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS IM_GRSNO,
            COALESCE(IM.IM_PSID, EM.EM_PSID) AS IM_PSID,
            CONVERT(VARBINARY(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS TD_SUBJ,
            CONVERT(VARCHAR(64), EF.EF_ID) AS EF_ID,
            CONVERT(VARBINARY(4000), EF.EF_NAME) AS EF_NAME,
            EF.EF_DATA,
            DATALENGTH(EF.EF_DATA) AS EF_DATA_LEN,
            EF.EF_PAGE
        FROM {em} EM
        LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO
        LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID
        WHERE (CONVERT(VARCHAR(64), IM.IM_PSID) = ? OR CONVERT(VARCHAR(64), EM.EM_PSID) = ?)
          AND EM.EM_GRSNO = ?
        ORDER BY EF.EF_PAGE
        """
        return self._query_all(sql, [login_user, login_user, tm_grsno])

    def list_incoming_todo(self, login_user: str):
        em = self._tbl("DCS1_EMAL_TMP")
        im = self._tbl("DCS1_IN_MAST")
        ef = self._tbl("DCS1_EMAL_FILE")

        if self.is_oracle:
            sql = f"""
            SELECT * FROM (
                SELECT
                    TRIM(IM.IM_GRSNO) AS IM_GRSNO,
                    TRIM(IM.IM_PSID) AS IM_PSID,
                    TRIM(COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS TD_SUBJ,
                    TRIM(EF.EF_ID) AS EF_ID,
                    TRIM(EF.EF_NAME) AS EF_NAME,
                    TRIM(EF.EF_PAGE) AS EF_PAGE
                FROM {im} IM
                LEFT JOIN {em} EM ON IM.IM_GRSNO = EM.EM_GRSNO
                LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID
                WHERE (TRIM(IM.IM_PSID) = :login_user OR TRIM(EM.EM_PSID) = :login_user)
                  AND IM.IM_CNCDT IS NULL
                ORDER BY EF.EF_PAGE
            )
            WHERE ROWNUM <= 60
            """
            return self._query_all(sql, {"login_user": str(login_user).strip()})

        # Sybase branch
        sql = self.SYB_INCOMING_TODO_LIST_SQL.format(em=em, im=im, ef=ef)
        return self._query_all(sql, [login_user, login_user])

    def get_file_by_ef_id(self, ef_id: str, page: str | None = None):
        sql, params = self._sql_file_by_ef_id(ef_id, page)
        return self._query_one(sql, params)

    def list_files_by_ef_id(self, ef_id: str, page: str | None = None):
        sql, params = self._sql_file_by_ef_id(ef_id, page)
        return self._query_all(sql, params)

    def _sql_file_by_ef_id(self, ef_id: str, page: str | None = None) -> tuple[str, list | dict]:
        ef = self._tbl("DCS1_EMAL_FILE")
        if self.is_oracle:
            where_page = " AND TRIM(EF.EF_PAGE) = :ef_page" if page else ""
            sql = f"""
            SELECT TRIM(EF.EF_NAME) AS EF_NAME, EF.EF_DATA AS EF_DATA
            FROM {ef} EF
            WHERE TRIM(EF.EF_ID) = :ef_id
            {where_page}
            """
            params: dict[str, str] = {"ef_id": str(ef_id or "").strip()}
            if page: params["ef_page"] = str(page or "").strip()
            return sql, params

        where_page = " AND CONVERT(VARCHAR(64), EF.EF_PAGE) = ?" if page else ""
        sql = f"""
        SELECT CONVERT(VARBINARY(4000), EF.EF_NAME) AS EF_NAME, EF.EF_DATA
        FROM {ef} EF
        WHERE CONVERT(VARCHAR(64), EF.EF_ID) = ?
        {where_page}
        """
        params_list = [str(ef_id or "").strip()]
        if page: params_list.append(str(page or "").strip())
        return sql, params_list

    def get_file_by_df_path(self, df_path: str):
        df = self._tbl("DCS0_DOC_FILE")
        if self.is_oracle:
            path_s = str(df_path or "").strip()
            sql = f"SELECT TRIM(DF.DF_NAME) AS EF_NAME, DF.DF_DATA FROM {df} DF WHERE TRIM(DF.DF_PATH) = :p"
            return self._query_one(sql, {"p": path_s})

        # Sybase datasets may contain padded/variant DF_PATH strings.
        # Keep exact-match first, then fallback to trimmed/normalized matching.
        path_raw = str(df_path or "")
        path_s = path_raw.strip()

        sql_exact = (
            f"SELECT CONVERT(VARBINARY(4000), DF.DF_NAME) AS EF_NAME, DF.DF_DATA "
            f"FROM {df} DF WHERE DF.DF_PATH = ?"
        )
        row = self._query_one(sql_exact, [path_raw])
        if row:
            return row

        if not path_s:
            return row

        sql_trim = (
            f"SELECT TOP 1 CONVERT(VARBINARY(4000), DF.DF_NAME) AS EF_NAME, DF.DF_DATA "
            f"FROM {df} DF "
            f"WHERE LTRIM(RTRIM(CONVERT(VARCHAR(1024), DF.DF_PATH))) = ?"
        )
        row = self._query_one(sql_trim, [path_s])
        if row:
            return row

        path_norm = path_s.replace("\\", "/")
        if path_norm != path_s:
            sql_norm = (
                f"SELECT TOP 1 CONVERT(VARBINARY(4000), DF.DF_NAME) AS EF_NAME, DF.DF_DATA "
                f"FROM {df} DF "
                f"WHERE REPLACE(LTRIM(RTRIM(CONVERT(VARCHAR(1024), DF.DF_PATH))), '\\\\', '/') = ?"
            )
            row = self._query_one(sql_norm, [path_norm])
            if row:
                return row

        return row

    def check_ownership(self, login_user: str, key_type: str, key_val: str) -> bool:
        tm, td = self._tbl("DCS3_TRST_MST"), self._tbl("DCS3_TRST_DAT")
        em, ef, im = self._tbl("DCS1_EMAL_TMP"), self._tbl("DCS1_EMAL_FILE"), self._tbl("DCS1_IN_MAST")

        if key_type == "EF":
            if self.is_oracle:
                sql = f"SELECT 1 FROM {em} EM JOIN {ef} EF ON EM.EM_FID = EF.EF_ID JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO WHERE (TRIM(IM.IM_PSID) = :u OR TRIM(EM.EM_PSID) = :u) AND TRIM(EF.EF_ID) = :v AND ROWNUM = 1"
                return bool(self._query_one(sql, {"u": login_user.strip(), "v": key_val.strip()}))
            sql = f"SELECT TOP 1 1 FROM {em} EM JOIN {ef} EF ON EM.EM_FID = EF.EF_ID JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO WHERE (CONVERT(VARCHAR(64), IM.IM_PSID) = ? OR CONVERT(VARCHAR(64), EM.EM_PSID) = ?) AND CONVERT(VARCHAR(64), EF.EF_ID) = ?"
            return bool(self._query_one(sql, [login_user, login_user, key_val]))

        # DF path check
        if self.is_oracle:
            sql = f"SELECT 1 FROM {tm} TM JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO WHERE TRIM(TM.TM_PSID) = :u AND TRIM(TD.TD_PATH) = :v AND ROWNUM = 1"
            return bool(self._query_one(sql, {"u": login_user.strip(), "v": key_val.strip()}))
        sql = f"SELECT TOP 1 1 FROM {tm} TM JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO WHERE CONVERT(VARCHAR(64), TM.TM_PSID) = ? AND TD.TD_PATH = ?"
        return bool(self._query_one(sql, [login_user, key_val]))

    def query_oracle_draft_documents_by_grsno(self, grsno: str, subject: str = ""):
        """
        Oracle three-block query #1:
        Draft Documents (formal doc formats only).
        """
        if not self.is_oracle:
            return []
        tm = self._tbl("DCS3_TRST_MST")
        td = self._tbl("DCS3_TRST_DAT")
        df = self._tbl("DCS0_DOC_FILE")
        subject_clause = ""
        params = {"grsno": str(grsno or "").strip()}
        if str(subject or "").strip():
            subject_clause = "AND TRIM(TD.TD_SUBJ) LIKE :subject_like ESCAPE '\\'"
            params["subject_like"] = self._like_value(subject)
        sql = f"""
        SELECT
            TRIM(TM.TM_GRSNO) AS TM_GRSNO,
            TM.TM_DATE AS TM_DATE,
            TRIM(TM.TM_PSID) AS TM_PSID,
            TRIM(TM.TM_NAME) AS TM_NAME,
            TRIM(TM.TM_RSTP) AS TM_RSTP,
            TRIM(TD.TD_FORMAT) AS TD_FORMAT,
            TRIM(TD.TD_SUBJ) AS TD_SUBJ,
            TRIM(TD.TD_PATH) AS TD_PATH,
            TRIM(DF.DF_NAME) AS DF_NAME,
            NVL(DBMS_LOB.GETLENGTH(DF.DF_DATA), 0) AS DF_DATA_LEN
        FROM {tm} TM
        JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO
        LEFT JOIN {df} DF ON TRIM(DF.DF_PATH) = TRIM(TD.TD_PATH)
        WHERE TD.TD_FORMAT IN ('簽呈', '呈', '令', '函', '便籤')
          AND TRIM(TM.TM_GRSNO) = :grsno
          {subject_clause}
        ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC, TD.TD_PATH
        """
        return self._query_all(sql, params)

    def query_oracle_draft_attachments_by_grsno(self, grsno: str, subject: str = ""):
        """
        Oracle three-block query #2:
        Draft Attachments (non-formal formats).
        """
        if not self.is_oracle:
            return []
        tm = self._tbl("DCS3_TRST_MST")
        td = self._tbl("DCS3_TRST_DAT")
        df = self._tbl("DCS0_DOC_FILE")
        subject_clause = ""
        params = {"grsno": str(grsno or "").strip()}
        if str(subject or "").strip():
            subject_clause = "AND TRIM(TD.TD_SUBJ) LIKE :subject_like ESCAPE '\\'"
            params["subject_like"] = self._like_value(subject)
        sql = f"""
        SELECT
            TRIM(TM.TM_GRSNO) AS TM_GRSNO,
            TM.TM_DATE AS TM_DATE,
            TRIM(TM.TM_PSID) AS TM_PSID,
            TRIM(TM.TM_NAME) AS TM_NAME,
            TRIM(TM.TM_RSTP) AS TM_RSTP,
            TRIM(TD.TD_FORMAT) AS TD_FORMAT,
            TRIM(TD.TD_SUBJ) AS TD_SUBJ,
            TRIM(TD.TD_PATH) AS TD_PATH,
            TRIM(DF.DF_NAME) AS DF_NAME,
            NVL(DBMS_LOB.GETLENGTH(DF.DF_DATA), 0) AS DF_DATA_LEN
        FROM {tm} TM
        JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO
        JOIN {df} DF ON TRIM(DF.DF_PATH) = TRIM(TD.TD_PATH)
        WHERE TD.TD_FORMAT NOT IN ('簽呈', '呈', '令', '函', '便籤')
          AND TRIM(TM.TM_GRSNO) = :grsno
          {subject_clause}
        ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC, TD.TD_PATH
        """
        return self._query_all(sql, params)

    def query_oracle_incoming_with_attachments_by_grsno(self, grsno: str, subject: str = ""):
        """
        Oracle three-block query #3:
        Incoming docs + attachments.
        """
        if not self.is_oracle:
            return []
        im = self._tbl("DCS1_IN_MAST")
        ef = self._tbl("DCS1_EMAL_FILE")
        em = self._tbl("DCS1_EMAL_TMP")

        params = {"grsno": str(grsno or "").strip()}
        subject_clause_primary = ""
        subject_clause_fallback = ""
        if str(subject or "").strip():
            params["subject_like"] = self._like_value(subject)
            subject_clause_primary = "AND TRIM(IM.IM_SUBJ) LIKE :subject_like ESCAPE '\\'"
            subject_clause_fallback = "AND TRIM(COALESCE(IM.IM_SUBJ, EM.EM_SUBJ)) LIKE :subject_like ESCAPE '\\'"
        sql_primary = f"""
        SELECT
            TRIM(IM.IM_GRSNO) AS IM_GRSNO,
            TRIM(IM.IM_PSID) AS IM_PSID,
            TRIM(IM.IM_SUBJ) AS IM_SUBJ,
            TRIM(EF.EF_NAME) AS EF_NAME,
            TRIM(EF.EF_ID) AS EF_ID,
            TRIM(EF.EF_PAGE) AS EF_PAGE,
            NVL(DBMS_LOB.GETLENGTH(EF.EF_DATA), 0) AS EF_DATA_LEN
        FROM {im} IM
        LEFT JOIN {ef} EF ON TRIM(IM.IM_GRSNO) = TRIM(EF.EF_GRSNO)
        WHERE TRIM(IM.IM_GRSNO) = :grsno
          {subject_clause_primary}
        ORDER BY EF.EF_PAGE
        """
        try:
            return self._query_all(sql_primary, params)
        except Exception:
            # Compatibility fallback for schemas without EF_GRSNO.
            sql_fallback = f"""
            SELECT
                TRIM(COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) AS IM_GRSNO,
                TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) AS IM_PSID,
                TRIM(COALESCE(IM.IM_SUBJ, EM.EM_SUBJ)) AS IM_SUBJ,
                TRIM(EF.EF_NAME) AS EF_NAME,
                TRIM(EF.EF_ID) AS EF_ID,
                TRIM(EF.EF_PAGE) AS EF_PAGE,
                NVL(DBMS_LOB.GETLENGTH(EF.EF_DATA), 0) AS EF_DATA_LEN
            FROM {im} IM
            LEFT JOIN {em} EM ON TRIM(IM.IM_GRSNO) = TRIM(EM.EM_GRSNO)
            LEFT JOIN {ef} EF ON TRIM(EM.EM_FID) = TRIM(EF.EF_ID)
            WHERE TRIM(IM.IM_GRSNO) = :grsno
              {subject_clause_fallback}
            ORDER BY EF.EF_PAGE
            """
            return self._query_all(sql_fallback, params)

    def search_incoming_advanced(
        self,
        *,
        grsno="",
        subject="",
        psids=None,
        limit=200,
        start_date: str = "",
        end_date: str = "",
    ):
        n = self._safe_limit(limit)
        em, im, ef = self._tbl("DCS1_EMAL_TMP"), self._tbl("DCS1_IN_MAST"), self._tbl("DCS1_EMAL_FILE")
        if self.is_oracle:
            clauses, params = [], {}
            if grsno: 
                clauses.append("AND TRIM(COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) LIKE :g ESCAPE '\\'")
                params["g"] = self._like_value(grsno)
            if subject:
                clauses.append("AND TRIM(COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) LIKE :s ESCAPE '\\'")
                params["s"] = self._like_value(subject)
            if start_date:
                clauses.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) >= TO_DATE(:start_date, 'YYYY-MM-DD')")
                params["start_date"] = start_date
            if end_date:
                clauses.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) < TO_DATE(:end_date, 'YYYY-MM-DD') + 1")
                params["end_date"] = end_date
            if psids:
                binds, bparams = self._oracle_in_clause_params("p", psids)
                clauses.append(f"AND TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) IN ({binds})")
                params.update(bparams)
            params["limit"] = n
            # Phase 1: 取得符合條件的前 n 份來文文號
            sql_p1 = (
                f"SELECT * FROM ("
                f"SELECT DISTINCT COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS GRSNO "
                f"FROM {em} EM "
                f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO "
                f"WHERE 1=1 {' '.join(clauses)} "
                f"ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC"
                f") WHERE ROWNUM <= :limit"
            )
            rows_p1 = self._query_all(sql_p1, params)
            ordered_grsnos = []
            seen = set()
            for r in rows_p1 or []:
                g = str(r[0] if len(r) > 0 and r[0] is not None else "").strip()
                if g and g not in seen:
                    seen.add(g)
                    ordered_grsnos.append(g)
            if not ordered_grsnos:
                return []

            # Phase 2: 依文號批次取得本文與附件明細
            binds_g, bparams_g = self._oracle_in_clause_params("g", ordered_grsnos)
            sql_p2 = (
                f"SELECT "
                f"TRIM(COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) AS IM_GRSNO, "
                f"TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) AS IM_PSID, "
                f"TRIM(COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS TD_SUBJ, "
                f"TRIM(EF.EF_ID) AS EF_ID, "
                f"TRIM(EF.EF_NAME) AS EF_NAME, "
                f"TRIM(EF.EF_PAGE) AS EF_PAGE "
                f"FROM {em} EM "
                f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO "
                f"LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID "
                f"WHERE COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) IN ({binds_g}) "
                f"ORDER BY 1 DESC, EF.EF_PAGE"
            )
            return self._query_all(sql_p2, bparams_g)

        # Sybase
        clauses: list[str] = []
        params: list[Any] = []
        if grsno:
            clauses.append("AND CONVERT(VARCHAR(64), COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) LIKE ? ESCAPE '\\'")
            params.append(self._like_value(grsno))
        if subject:
            clauses.append("AND CONVERT(VARCHAR(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) LIKE ? ESCAPE '\\'")
            params.append(self._like_value(subject))
        if start_date:
            clauses.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) < DATEADD(day, 1, ?)")
            params.append(end_date)
        normalized_psids = self._normalize_psids(psids)
        if normalized_psids:
            placeholders = ",".join(["?"] * len(normalized_psids))
            clauses.append(f"AND CONVERT(VARCHAR(64), COALESCE(IM.IM_PSID, EM.EM_PSID)) IN ({placeholders})")
            params.extend(normalized_psids)

        # Phase 1: 取得符合條件的前 n 份來文文號
        sql_p1 = (
            f"SELECT DISTINCT TOP {n} "
            f"COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) "
            f"FROM {em} EM "
            f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO "
            f"WHERE 1=1 {' '.join(clauses)} "
            f"ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC"
        )
        rows_p1 = self._query_all(sql_p1, params)
        ordered_grsnos = []
        seen = set()
        for r in rows_p1 or []:
            g = str(r[0] if len(r) > 0 and r[0] is not None else "").strip()
            if g and g not in seen:
                seen.add(g)
                ordered_grsnos.append(g)
        if not ordered_grsnos:
            return []

        # Phase 2: 依文號批次取得本文與附件明細
        placeholders_g = ",".join(["?"] * len(ordered_grsnos))
        sql_p2 = (
            f"SELECT "
            f"COALESCE(IM.IM_GRSNO, EM.EM_GRSNO), "
            f"COALESCE(IM.IM_PSID, EM.EM_PSID), "
            f"CONVERT(VARBINARY(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)), "
            f"EF.EF_ID, "
            f"CONVERT(VARBINARY(4000), EF.EF_NAME), "
            f"EF.EF_PAGE "
            f"FROM {em} EM "
            f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO "
            f"LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID "
            f"WHERE COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) IN ({placeholders_g}) "
            f"ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC, EF.EF_PAGE"
        )
        return self._query_all(sql_p2, ordered_grsnos)

    def search_trst_advanced(
        self,
        *,
        grsno="",
        subject="",
        psids=None,
        limit=200,
        start_date: str = "",
        end_date: str = "",
    ):
        n = self._safe_limit(limit)
        tm, td, df = self._tbl("DCS3_TRST_MST"), self._tbl("DCS3_TRST_DAT"), self._tbl("DCS0_DOC_FILE")
        if self.is_oracle:
            clauses, params = [], {}
            if grsno: 
                clauses.append("AND TRIM(TM.TM_GRSNO) LIKE :g ESCAPE '\\'")
                params["g"] = self._like_value(grsno)
            if subject:
                clauses.append("AND TRIM(TD.TD_SUBJ) LIKE :s ESCAPE '\\'")
                params["s"] = self._like_value(subject)
            if start_date:
                clauses.append("AND TM.TM_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')")
                params["start_date"] = start_date
            if end_date:
                clauses.append("AND TM.TM_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1")
                params["end_date"] = end_date
            if psids:
                binds, bparams = self._oracle_in_clause_params("p", psids)
                clauses.append(f"AND TRIM(TM.TM_PSID) IN ({binds})")
                params.update(bparams)
            params["limit"] = n

            # Phase 1: 取得符合條件的前 n 份公文 TM_SNO
            if subject:
                sql_p1 = (
                    f"SELECT * FROM ("
                    f"SELECT DISTINCT TM.TM_SNO, TM.TM_DATE "
                    f"FROM {tm} TM "
                    f"JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO "
                    f"WHERE 1=1 {' '.join(clauses)} "
                    f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC"
                    f") WHERE ROWNUM <= :limit"
                )
            else:
                sql_p1 = (
                    f"SELECT * FROM ("
                    f"SELECT TM.TM_SNO, TM.TM_DATE "
                    f"FROM {tm} TM "
                    f"WHERE 1=1 {' '.join(clauses)} "
                    f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC"
                    f") WHERE ROWNUM <= :limit"
                )
            rows_p1 = self._query_all(sql_p1, params)
            ordered_snos = []
            seen = set()
            for r in rows_p1 or []:
                sno = str(r[0] if len(r) > 0 and r[0] is not None else "").strip()
                if sno and sno not in seen:
                    seen.add(sno)
                    ordered_snos.append(sno)
            if not ordered_snos:
                return []

            # Phase 2: 依 SNO 批次取得簽稿與附件明細
            binds_s, bparams_s = self._oracle_in_clause_params("sno", ordered_snos)
            sql_p2 = (
                f"SELECT "
                f"TRIM(TM.TM_GRSNO), TM.TM_DATE, TRIM(TM.TM_PSID), TRIM(TM.TM_NAME), TRIM(TM.TM_RSTP), "
                f"TRIM(TD.TD_FORMAT), TRIM(TD.TD_SUBJ), TRIM(TD.TD_PATH), TRIM(DF.DF_NAME), "
                f"NVL(DBMS_LOB.GETLENGTH(DF.DF_DATA), 0) "
                f"FROM {tm} TM "
                f"JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO "
                f"LEFT JOIN {df} DF ON TRIM(DF.DF_PATH) = TRIM(TD.TD_PATH) "
                f"WHERE TM.TM_SNO IN ({binds_s}) "
                f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC, TD.TD_PATH"
            )
            return self._query_all(sql_p2, bparams_s)

        # Sybase
        clauses: list[str] = []
        params: list[Any] = []
        if grsno:
            clauses.append("AND CONVERT(VARCHAR(64), TM.TM_GRSNO) LIKE ? ESCAPE '\\'")
            params.append(self._like_value(grsno))
        if subject:
            clauses.append("AND CONVERT(VARCHAR(4000), TD.TD_SUBJ) LIKE ? ESCAPE '\\'")
            params.append(self._like_value(subject))
        if start_date:
            clauses.append("AND TM.TM_DATE >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("AND TM.TM_DATE < DATEADD(day, 1, ?)")
            params.append(end_date)
        normalized_psids = self._normalize_psids(psids)
        if normalized_psids:
            placeholders = ",".join(["?"] * len(normalized_psids))
            clauses.append(f"AND CONVERT(VARCHAR(64), TM.TM_PSID) IN ({placeholders})")
            params.extend(normalized_psids)

        # Phase 1: 取得符合條件的前 n 份公文 TM_SNO
        if subject:
            sql_p1 = (
                f"SELECT DISTINCT TOP {n} TM.TM_SNO, TM.TM_DATE "
                f"FROM {tm} TM "
                f"JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO "
                f"WHERE 1=1 {' '.join(clauses)} "
                f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC"
            )
        else:
            sql_p1 = (
                f"SELECT TOP {n} TM.TM_SNO, TM.TM_DATE "
                f"FROM {tm} TM "
                f"WHERE 1=1 {' '.join(clauses)} "
                f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC"
            )
        rows_p1 = self._query_all(sql_p1, params)
        ordered_snos = []
        seen = set()
        for r in rows_p1 or []:
            sno = str(r[0] if len(r) > 0 and r[0] is not None else "").strip()
            if sno and sno not in seen:
                seen.add(sno)
                ordered_snos.append(sno)
        if not ordered_snos:
            return []

        # Phase 2: 依 SNO 批次取得簽稿與附件明細
        placeholders_s = ",".join(["?"] * len(ordered_snos))
        sql_p2 = (
            f"SELECT "
            f"TM.TM_GRSNO, TM.TM_DATE, TM.TM_PSID, "
            f"CONVERT(VARBINARY(400), TM.TM_NAME), "
            f"CONVERT(VARBINARY(400), TM.TM_RSTP), "
            f"CONVERT(VARBINARY(400), TD.TD_FORMAT), "
            f"CONVERT(VARBINARY(4000), TD.TD_SUBJ), "
            f"TD.TD_PATH, "
            f"CONVERT(VARBINARY(400), DF.DF_NAME), "
            f"DATALENGTH(DF.DF_DATA) "
            f"FROM {tm} TM "
            f"JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO "
            f"LEFT JOIN {df} DF ON DF.DF_PATH = TD.TD_PATH "
            f"WHERE TM.TM_SNO IN ({placeholders_s}) "
            f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC, TD.TD_PATH"
        )
        return self._query_all(sql_p2, ordered_snos)

    def get_debug_sql_statements(
        self,
        *,
        grsno: str = "",
        subject: str = "",
        psids: Sequence[str] | None = None,
        limit: int = 200,
        start_date: str = "",
        end_date: str = "",
        executed_snos: Sequence[str] | None = None,
        executed_grsnos: Sequence[str] | None = None,
        handler_name: str = "",
    ) -> dict[str, Any]:
        """
        為四大類別產生查詢 SQL 語法與執行說明，供前端驗證與手動排查使用：
        1) 簽、稿主檔清單（DF BLOB）
        2) 簽、稿附件清單（DF BLOB）
        3) 來文主旨清單
        4) 來文附件清單（EF BLOB）
        """
        n = self._safe_limit(limit)
        target_obj = getattr(self, "target", None)
        plant_name = getattr(target_obj, "plant", "MPC") if target_obj else "MPC"
        db_type = "Oracle" if self.is_oracle else "Sybase ASE"
        
        tm = self._tbl("DCS3_TRST_MST")
        td = self._tbl("DCS3_TRST_DAT")
        df = self._tbl("DCS0_DOC_FILE")
        em = self._tbl("DCS3_EDOC_MST")
        im = self._tbl("DCS3_INCOMING_MST")
        ef = self._tbl("DCS3_EDOC_FILE")

        norm_psids = self._normalize_psids(psids)
        psids_display = ", ".join(norm_psids) if norm_psids else "(未指定工號)"
        handler_desc = f"{handler_name} (工號: {psids_display})" if handler_name else psids_display
        date_desc = f"{start_date} ~ {end_date}" if (start_date or end_date) else "(未指定)"

        # --- 組裝 簽、稿 (Trst) Phase 1 SQL ---
        trst_clauses_exec: list[str] = []
        trst_clauses_prep: list[str] = []
        trst_prep_params: list[Any] = []

        if self.is_oracle:
            if grsno:
                trst_clauses_exec.append(f"AND TRIM(TM.TM_GRSNO) LIKE '%{grsno}%' ESCAPE '\\'")
                trst_clauses_prep.append("AND TRIM(TM.TM_GRSNO) LIKE :g ESCAPE '\\'")
                trst_prep_params.append(f"%{grsno}%")
            if subject:
                trst_clauses_exec.append(f"AND TRIM(TD.TD_SUBJ) LIKE '%{subject}%' ESCAPE '\\'")
                trst_clauses_prep.append("AND TRIM(TD.TD_SUBJ) LIKE :s ESCAPE '\\'")
                trst_prep_params.append(f"%{subject}%")
            if start_date:
                trst_clauses_exec.append(f"AND TM.TM_DATE >= TO_DATE('{start_date}', 'YYYY-MM-DD')")
                trst_clauses_prep.append("AND TM.TM_DATE >= TO_DATE(:start_date, 'YYYY-MM-DD')")
                trst_prep_params.append(start_date)
            if end_date:
                trst_clauses_exec.append(f"AND TM.TM_DATE < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1")
                trst_clauses_prep.append("AND TM.TM_DATE < TO_DATE(:end_date, 'YYYY-MM-DD') + 1")
                trst_prep_params.append(end_date)
            if norm_psids:
                quoted = ", ".join([f"'{p}'" for p in norm_psids])
                trst_clauses_exec.append(f"AND TRIM(TM.TM_PSID) IN ({quoted})")
                binds_p, _ = self._oracle_in_clause_params("p", norm_psids)
                trst_clauses_prep.append(f"AND TRIM(TM.TM_PSID) IN ({binds_p})")
                trst_prep_params.extend(norm_psids)

            clauses_trst_str_exec = "\n  ".join(trst_clauses_exec) if trst_clauses_exec else "  -- (無額外過濾條件)"
            clauses_trst_str_prep = "\n  ".join(trst_clauses_prep) if trst_clauses_prep else "  -- (無額外過濾條件)"

            trst_p1_exec = (
                f"SELECT * FROM (\n"
                f"  SELECT DISTINCT TM.TM_SNO, TM.TM_DATE\n"
                f"  FROM {tm} TM\n"
                f"  JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO\n"
                f"  WHERE 1=1\n"
                f"  {clauses_trst_str_exec}\n"
                f"  ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC\n"
                f") WHERE ROWNUM <= {n};"
            )
            trst_p1_prep = (
                f"SELECT * FROM (\n"
                f"  SELECT DISTINCT TM.TM_SNO, TM.TM_DATE\n"
                f"  FROM {tm} TM\n"
                f"  JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO\n"
                f"  WHERE 1=1\n"
                f"  {clauses_trst_str_prep}\n"
                f"  ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC\n"
                f") WHERE ROWNUM <= :limit;"
            )
        else:
            # Sybase ASE
            if grsno:
                trst_clauses_exec.append(f"AND CONVERT(VARCHAR(64), TM.TM_GRSNO) LIKE '%{grsno}%' ESCAPE '\\'")
                trst_clauses_prep.append("AND CONVERT(VARCHAR(64), TM.TM_GRSNO) LIKE ? ESCAPE '\\'")
                trst_prep_params.append(f"%{grsno}%")
            if subject:
                trst_clauses_exec.append(f"AND CONVERT(VARCHAR(4000), TD.TD_SUBJ) LIKE '%{subject}%' ESCAPE '\\'")
                trst_clauses_prep.append("AND CONVERT(VARCHAR(4000), TD.TD_SUBJ) LIKE ? ESCAPE '\\'")
                trst_prep_params.append(f"%{subject}%")
            if start_date:
                trst_clauses_exec.append(f"AND TM.TM_DATE >= '{start_date}'")
                trst_clauses_prep.append("AND TM.TM_DATE >= ?")
                trst_prep_params.append(start_date)
            if end_date:
                trst_clauses_exec.append(f"AND TM.TM_DATE < DATEADD(day, 1, '{end_date}')")
                trst_clauses_prep.append("AND TM.TM_DATE < DATEADD(day, 1, ?)")
                trst_prep_params.append(end_date)
            if norm_psids:
                quoted = ", ".join([f"'{p}'" for p in norm_psids])
                trst_clauses_exec.append(f"AND CONVERT(VARCHAR(64), TM.TM_PSID) IN ({quoted})")
                ph = ",".join(["?"] * len(norm_psids))
                trst_clauses_prep.append(f"AND CONVERT(VARCHAR(64), TM.TM_PSID) IN ({ph})")
                trst_prep_params.extend(norm_psids)

            clauses_trst_str_exec = "\n  ".join(trst_clauses_exec) if trst_clauses_exec else "  -- (無額外過濾條件)"
            clauses_trst_str_prep = "\n  ".join(trst_clauses_prep) if trst_clauses_prep else "  -- (無額外過濾條件)"

            trst_p1_exec = (
                f"SELECT DISTINCT TOP {n} TM.TM_SNO, TM.TM_DATE\n"
                f"FROM {tm} TM\n"
                f"JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO\n"
                f"WHERE 1=1\n"
                f"  {clauses_trst_str_exec}\n"
                f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC;"
            )
            trst_p1_prep = (
                f"SELECT DISTINCT TOP {n} TM.TM_SNO, TM.TM_DATE\n"
                f"FROM {tm} TM\n"
                f"JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO\n"
                f"WHERE 1=1\n"
                f"  {clauses_trst_str_prep}\n"
                f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC;"
            )

        # Trst Phase 2
        snos_sample = list(executed_snos[:5]) if executed_snos else ["<Phase 1 取得之 TM_SNO 清單>"]
        snos_in_sql = ", ".join([f"'{s}'" for s in snos_sample])

        if self.is_oracle:
            trst_p2_exec = (
                f"SELECT \n"
                f"    TRIM(TM.TM_GRSNO) AS TM_GRSNO, TM.TM_DATE, TRIM(TM.TM_PSID) AS TM_PSID, \n"
                f"    TRIM(TM.TM_NAME) AS TM_NAME, TRIM(TM.TM_RSTP) AS TM_RSTP, \n"
                f"    TRIM(TD.TD_FORMAT) AS TD_FORMAT, TRIM(TD.TD_SUBJ) AS TD_SUBJ, \n"
                f"    TRIM(TD.TD_PATH) AS TD_PATH, TRIM(DF.DF_NAME) AS DF_NAME, \n"
                f"    NVL(DBMS_LOB.GETLENGTH(DF.DF_DATA), 0) AS BLOB_SIZE\n"
                f"FROM {tm} TM\n"
                f"JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO\n"
                f"LEFT JOIN {df} DF ON TRIM(DF.DF_PATH) = TRIM(TD.TD_PATH)\n"
                f"WHERE TM.TM_SNO IN ({snos_in_sql})\n"
                f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC, TD.TD_PATH;"
            )
        else:
            trst_p2_exec = (
                f"SELECT \n"
                f"    TM.TM_GRSNO, TM.TM_DATE, TM.TM_PSID,\n"
                f"    CONVERT(VARBINARY(400), TM.TM_NAME) AS TM_NAME,\n"
                f"    CONVERT(VARBINARY(400), TM.TM_RSTP) AS TM_RSTP,\n"
                f"    CONVERT(VARBINARY(400), TD.TD_FORMAT) AS TD_FORMAT,\n"
                f"    CONVERT(VARBINARY(4000), TD.TD_SUBJ) AS TD_SUBJ,\n"
                f"    TD.TD_PATH,\n"
                f"    CONVERT(VARBINARY(400), DF.DF_NAME) AS DF_NAME,\n"
                f"    DATALENGTH(DF.DF_DATA) AS BLOB_SIZE\n"
                f"FROM {tm} TM\n"
                f"JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO\n"
                f"LEFT JOIN {df} DF ON DF.DF_PATH = TD.TD_PATH\n"
                f"WHERE TM.TM_SNO IN ({snos_in_sql})\n"
                f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC, TD.TD_PATH;"
            )

        # --- 組裝 來文 (Incoming) Phase 1 SQL ---
        inc_clauses_exec: list[str] = []
        inc_clauses_prep: list[str] = []
        inc_prep_params: list[Any] = []

        if self.is_oracle:
            if grsno:
                inc_clauses_exec.append(f"AND TRIM(COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) LIKE '%{grsno}%' ESCAPE '\\'")
                inc_clauses_prep.append("AND TRIM(COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) LIKE :g ESCAPE '\\'")
                inc_prep_params.append(f"%{grsno}%")
            if subject:
                inc_clauses_exec.append(f"AND TRIM(COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) LIKE '%{subject}%' ESCAPE '\\'")
                inc_clauses_prep.append("AND TRIM(COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) LIKE :s ESCAPE '\\'")
                inc_prep_params.append(f"%{subject}%")
            if start_date:
                inc_clauses_exec.append(f"AND COALESCE(IM.IM_DATE, EM.EM_DATE) >= TO_DATE('{start_date}', 'YYYY-MM-DD')")
                inc_clauses_prep.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) >= TO_DATE(:start_date, 'YYYY-MM-DD')")
                inc_prep_params.append(start_date)
            if end_date:
                inc_clauses_exec.append(f"AND COALESCE(IM.IM_DATE, EM.EM_DATE) < TO_DATE('{end_date}', 'YYYY-MM-DD') + 1")
                inc_clauses_prep.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) < TO_DATE(:end_date, 'YYYY-MM-DD') + 1")
                inc_prep_params.append(end_date)
            if norm_psids:
                quoted = ", ".join([f"'{p}'" for p in norm_psids])
                inc_clauses_exec.append(f"AND TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) IN ({quoted})")
                binds_p, _ = self._oracle_in_clause_params("p", norm_psids)
                inc_clauses_prep.append(f"AND TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) IN ({binds_p})")
                inc_prep_params.extend(norm_psids)

            clauses_inc_str_exec = "\n  ".join(inc_clauses_exec) if inc_clauses_exec else "  -- (無額外過濾條件)"
            clauses_inc_str_prep = "\n  ".join(inc_clauses_prep) if inc_clauses_prep else "  -- (無額外過濾條件)"

            inc_p1_exec = (
                f"SELECT * FROM (\n"
                f"  SELECT DISTINCT COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS GRSNO\n"
                f"  FROM {em} EM\n"
                f"  LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO\n"
                f"  WHERE 1=1\n"
                f"  {clauses_inc_str_exec}\n"
                f"  ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC\n"
                f") WHERE ROWNUM <= {n};"
            )
            inc_p1_prep = (
                f"SELECT * FROM (\n"
                f"  SELECT DISTINCT COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS GRSNO\n"
                f"  FROM {em} EM\n"
                f"  LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO\n"
                f"  WHERE 1=1\n"
                f"  {clauses_inc_str_prep}\n"
                f"  ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC\n"
                f") WHERE ROWNUM <= :limit;"
            )
        else:
            # Sybase ASE
            if grsno:
                inc_clauses_exec.append(f"AND CONVERT(VARCHAR(64), COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) LIKE '%{grsno}%' ESCAPE '\\'")
                inc_clauses_prep.append("AND CONVERT(VARCHAR(64), COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) LIKE ? ESCAPE '\\'")
                inc_prep_params.append(f"%{grsno}%")
            if subject:
                inc_clauses_exec.append(f"AND CONVERT(VARCHAR(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) LIKE '%{subject}%' ESCAPE '\\'")
                inc_clauses_prep.append("AND CONVERT(VARCHAR(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) LIKE ? ESCAPE '\\'")
                inc_prep_params.append(f"%{subject}%")
            if start_date:
                inc_clauses_exec.append(f"AND COALESCE(IM.IM_DATE, EM.EM_DATE) >= '{start_date}'")
                inc_clauses_prep.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) >= ?")
                inc_prep_params.append(start_date)
            if end_date:
                inc_clauses_exec.append(f"AND COALESCE(IM.IM_DATE, EM.EM_DATE) < DATEADD(day, 1, '{end_date}')")
                inc_clauses_prep.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) < DATEADD(day, 1, ?)")
                inc_prep_params.append(end_date)
            if norm_psids:
                quoted = ", ".join([f"'{p}'" for p in norm_psids])
                inc_clauses_exec.append(f"AND CONVERT(VARCHAR(64), COALESCE(IM.IM_PSID, EM.EM_PSID)) IN ({quoted})")
                ph = ",".join(["?"] * len(norm_psids))
                inc_clauses_prep.append(f"AND CONVERT(VARCHAR(64), COALESCE(IM.IM_PSID, EM.EM_PSID)) IN ({ph})")
                inc_prep_params.extend(norm_psids)

            clauses_inc_str_exec = "\n  ".join(inc_clauses_exec) if inc_clauses_exec else "  -- (無額外過濾條件)"
            clauses_inc_str_prep = "\n  ".join(inc_clauses_prep) if inc_clauses_prep else "  -- (無額外過濾條件)"

            inc_p1_exec = (
                f"SELECT DISTINCT TOP {n}\n"
                f"    COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS GRSNO\n"
                f"FROM {em} EM\n"
                f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO\n"
                f"WHERE 1=1\n"
                f"  {clauses_inc_str_exec}\n"
                f"ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC;"
            )
            inc_p1_prep = (
                f"SELECT DISTINCT TOP {n}\n"
                f"    COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS GRSNO\n"
                f"FROM {em} EM\n"
                f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO\n"
                f"WHERE 1=1\n"
                f"  {clauses_inc_str_prep}\n"
                f"ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC;"
            )

        # Incoming Phase 2
        grsnos_sample = list(executed_grsnos[:5]) if executed_grsnos else ["<Phase 1 取得之 GRSNO 清單>"]
        grsnos_in_sql = ", ".join([f"'{g}'" for g in grsnos_sample])

        if self.is_oracle:
            inc_p2_exec = (
                f"SELECT \n"
                f"    TRIM(COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) AS IM_GRSNO, \n"
                f"    TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) AS IM_PSID, \n"
                f"    TRIM(COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS TD_SUBJ, \n"
                f"    TRIM(EF.EF_ID) AS EF_ID, \n"
                f"    TRIM(EF.EF_NAME) AS EF_NAME, \n"
                f"    TRIM(EF.EF_PAGE) AS EF_PAGE \n"
                f"FROM {em} EM\n"
                f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO\n"
                f"LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID\n"
                f"WHERE COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) IN ({grsnos_in_sql})\n"
                f"ORDER BY 1 DESC, EF.EF_PAGE;"
            )
        else:
            inc_p2_exec = (
                f"SELECT \n"
                f"    COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) AS GRSNO,\n"
                f"    COALESCE(IM.IM_PSID, EM.EM_PSID) AS PSID,\n"
                f"    CONVERT(VARBINARY(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS SUBJ,\n"
                f"    EF.EF_ID,\n"
                f"    CONVERT(VARBINARY(4000), EF.EF_NAME) AS EF_NAME,\n"
                f"    EF.EF_PAGE\n"
                f"FROM {em} EM\n"
                f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO\n"
                f"LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID\n"
                f"WHERE COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) IN ({grsnos_in_sql})\n"
                f"ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC, EF.EF_PAGE;"
            )

        # BLOB SQLs
        sql_df_blob = (
            f"-- 讀取簽稿檔案二進位內容 (DF BLOB)\n"
            f"SELECT DF_DATA \n"
            f"FROM {df} DF \n"
            f"WHERE DF.DF_PATH = '<點選預覽之TD_PATH，例如 /doc/archive/.../doc.di>';"
        )
        sql_ef_blob = (
            f"-- 讀取來文電子附件二進位內容 (EF BLOB)\n"
            f"SELECT EF_DATA \n"
            f"FROM {ef} EF \n"
            f"WHERE EF.EF_ID = '<點選預覽之EF_ID>' AND EF.EF_PAGE = <頁次，例如 1>;"
        )

        header_common = (
            f"-- 資料庫核心：{db_type} | 廠別代碼：{plant_name}\n"
            f"-- 查詢條件：相關號={grsno or '(未指定)'} | 主旨={subject or '(未指定)'}\n"
            f"-- 承辦人員：{handler_desc}\n"
            f"-- 日期區間：{date_desc} | 筆數上限：{n}\n"
        )

        # 1) 簽、稿主檔清單 (DF BLOB)
        text_draft_docs = (
            f"-- ============================================================================\n"
            f"-- 【1) 簽、稿主檔清單（DF BLOB）查詢語法】\n"
            f"-- 業務定義：簽稿主體公文（簽、呈、令、函、便等本文）。\n"
            f"-- 資料來源：{tm} 關聯 {td}，電子主檔關聯 {df} (TD.TD_PATH = DF.DF_PATH)。\n"
            f"-- 篩選原則：由 TD_FORMAT 符合本文主檔格式篩選出主檔列。\n"
            f"{header_common}"
            f"-- ============================================================================\n\n"
            f"-- [Phase 1: 依條件篩選前 {n} 筆簽稿案號清單 (TM_SNO)]\n"
            f"{trst_p1_exec}\n\n"
            f"-- [Phase 2: 依 TM_SNO 批次擷取簽稿主檔與本文關聯 (平坦查詢，無衍生表限制)]\n"
            f"{trst_p2_exec}\n\n"
            f"-- [Phase 1 參數化 Prepared SQL 參考]\n"
            f"{trst_p1_prep}\n"
            f"-- 參數值: {trst_prep_params}\n\n"
            f"-- [BLOB 實體檔案內容提取語法]\n"
            f"{sql_df_blob}\n"
        )

        # 2) 簽、稿附件清單 (DF BLOB)
        text_draft_attach = (
            f"-- ============================================================================\n"
            f"-- 【2) 簽、稿附件清單（DF BLOB）查詢語法】\n"
            f"-- 業務定義：簽稿案件所掛載之參考附件或非主文格式檔案。\n"
            f"-- 資料來源：{tm} 關聯 {td}，附件檔名與實體檔案存於 {df}。\n"
            f"-- 篩選原則：具有 DF_NAME 或 TD_FORMAT 屬於非主文附件格式。\n"
            f"{header_common}"
            f"-- ============================================================================\n\n"
            f"-- [Phase 1: 依條件篩選前 {n} 筆簽稿案號清單 (TM_SNO)]\n"
            f"{trst_p1_exec}\n\n"
            f"-- [Phase 2: 依 TM_SNO 批次擷取簽稿附件明細]\n"
            f"{trst_p2_exec}\n\n"
            f"-- [Phase 1 參數化 Prepared SQL 參考]\n"
            f"{trst_p1_prep}\n"
            f"-- 參數值: {trst_prep_params}\n\n"
            f"-- [BLOB 實體檔案內容提取語法]\n"
            f"{sql_df_blob}\n"
        )

        # 3) 來文主旨清單
        text_incoming_docs = (
            f"-- ============================================================================\n"
            f"-- 【3) 來文主旨清單 查詢語法】\n"
            f"-- 業務定義：外機關來文之收文登記案情、主旨、承辦人與案件摘要。\n"
            f"-- 資料來源：{em} (電子公文主表) LEFT JOIN {im} (收文主表)。\n"
            f"-- 核心欄位：COALESCE(IM_GRSNO, EM_GRSNO), COALESCE(EM_SUBJ, IM_SUBJ), COALESCE(IM_PSID, EM_PSID)\n"
            f"{header_common}"
            f"-- ============================================================================\n\n"
            f"-- [Phase 1: 依條件篩選前 {n} 筆來文文號清單 (GRSNO)]\n"
            f"{inc_p1_exec}\n\n"
            f"-- [Phase 2: 依 GRSNO 批次擷取來文主旨與摘要明細]\n"
            f"{inc_p2_exec}\n\n"
            f"-- [Phase 1 參數化 Prepared SQL 參考]\n"
            f"{inc_p1_prep}\n"
            f"-- 參數值: {inc_prep_params}\n"
        )

        # 4) 來文附件清單 (EF BLOB)
        text_incoming_attach = (
            f"-- ============================================================================\n"
            f"-- 【4) 來文附件清單（EF BLOB）查詢語法】\n"
            f"-- 業務定義：外機關來文夾帶之電子附件（PDF、圖檔、公文本文附件等）。\n"
            f"-- 資料來源：{em} (電子公文主表) LEFT JOIN {ef} (電子檔案表) ON EM.EM_FID = EF.EF_ID。\n"
            f"-- 核心欄位：EF_ID (附件代碼), EF_NAME (附件檔名), EF_PAGE (頁次)\n"
            f"{header_common}"
            f"-- ============================================================================\n\n"
            f"-- [Phase 1: 依條件篩選前 {n} 筆來文文號清單 (GRSNO)]\n"
            f"{inc_p1_exec}\n\n"
            f"-- [Phase 2: 依 GRSNO 批次擷取來文夾帶之電子附件清單]\n"
            f"{inc_p2_exec}\n\n"
            f"-- [Phase 1 參數化 Prepared SQL 參考]\n"
            f"{inc_p1_prep}\n"
            f"-- 參數值: {inc_prep_params}\n\n"
            f"-- [BLOB 實體檔案內容提取語法 (依 EF_ID 與 EF_PAGE)]\n"
            f"{sql_ef_blob}\n"
        )

        return {
            "draft_docs": {
                "title": "1) 簽、稿主檔清單（DF BLOB）",
                "phase1_sql": trst_p1_exec,
                "phase2_sql": trst_p2_exec,
                "blob_sql": sql_df_blob,
                "full_text": text_draft_docs,
            },
            "draft_attachments": {
                "title": "2) 簽、稿附件清單（DF BLOB）",
                "phase1_sql": trst_p1_exec,
                "phase2_sql": trst_p2_exec,
                "blob_sql": sql_df_blob,
                "full_text": text_draft_attach,
            },
            "incoming_docs": {
                "title": "3) 來文主旨清單",
                "phase1_sql": inc_p1_exec,
                "phase2_sql": inc_p2_exec,
                "full_text": text_incoming_docs,
            },
            "incoming_attachments": {
                "title": "4) 來文附件清單（EF BLOB）",
                "phase1_sql": inc_p1_exec,
                "phase2_sql": inc_p2_exec,
                "blob_sql": sql_ef_blob,
                "full_text": text_incoming_attach,
            },
        }


