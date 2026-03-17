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
    def _safe_limit(limit: int, default: int = 200, max_limit: int = 1000) -> int:
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

        sql = f"SELECT CONVERT(VARBINARY(4000), DF.DF_NAME) AS EF_NAME, DF.DF_DATA FROM {df} DF WHERE DF.DF_PATH = ?"
        return self._query_one(sql, [df_path])

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

    def search_incoming_advanced(self, *, grsno="", subject="", psids=None, limit=200, days_ago=None):
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
            if days_ago:
                clauses.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) >= SYSDATE - :d")
                params["d"] = days_ago
            if psids:
                binds, bparams = self._oracle_in_clause_params("p", psids)
                clauses.append(f"AND TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) IN ({binds})")
                params.update(bparams)
            params["limit"] = n
            sql = f"SELECT * FROM (SELECT TRIM(COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) AS IM_GRSNO, TRIM(COALESCE(IM.IM_PSID, EM.EM_PSID)) AS IM_PSID, TRIM(COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) AS TD_SUBJ, TRIM(EF.EF_ID) AS EF_ID, TRIM(EF.EF_NAME) AS EF_NAME, TRIM(EF.EF_PAGE) AS EF_PAGE FROM {em} EM LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID WHERE 1=1 {' '.join(clauses)} ORDER BY 1 DESC) WHERE ROWNUM <= :limit"
            return self._query_all(sql, params)
        # Sybase
        clauses: list[str] = []
        params: list[Any] = []
        if grsno:
            clauses.append("AND CONVERT(VARCHAR(64), COALESCE(IM.IM_GRSNO, EM.EM_GRSNO)) LIKE ? ESCAPE '\\'")
            params.append(self._like_value(grsno))
        if subject:
            clauses.append("AND CONVERT(VARCHAR(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)) LIKE ? ESCAPE '\\'")
            params.append(self._like_value(subject))
        if days_ago:
            clauses.append("AND COALESCE(IM.IM_DATE, EM.EM_DATE) >= DATEADD(day, -?, GETDATE())")
            params.append(int(days_ago))
        normalized_psids = self._normalize_psids(psids)
        if normalized_psids:
            placeholders = ",".join(["?"] * len(normalized_psids))
            clauses.append(f"AND CONVERT(VARCHAR(64), COALESCE(IM.IM_PSID, EM.EM_PSID)) IN ({placeholders})")
            params.extend(normalized_psids)
        sql = (
            f"SELECT TOP {n} "
            f"COALESCE(IM.IM_GRSNO, EM.EM_GRSNO), "
            f"COALESCE(IM.IM_PSID, EM.EM_PSID), "
            f"CONVERT(VARBINARY(4000), COALESCE(EM.EM_SUBJ, IM.IM_SUBJ)), "
            f"EF.EF_ID, "
            f"CONVERT(VARBINARY(4000), EF.EF_NAME), "
            f"EF.EF_PAGE "
            f"FROM {em} EM "
            f"LEFT JOIN {im} IM ON EM.EM_GRSNO = IM.IM_GRSNO "
            f"LEFT JOIN {ef} EF ON EM.EM_FID = EF.EF_ID "
            f"WHERE 1=1 {' '.join(clauses)} "
            f"ORDER BY COALESCE(IM.IM_GRSNO, EM.EM_GRSNO) DESC, EF.EF_PAGE"
        )
        return self._query_all(sql, params)

    def search_trst_advanced(self, *, grsno="", subject="", psids=None, limit=200, days_ago=None):
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
            if days_ago:
                clauses.append("AND TM.TM_DATE >= SYSDATE - :d")
                params["d"] = days_ago
            if psids:
                binds, bparams = self._oracle_in_clause_params("p", psids)
                clauses.append(f"AND TRIM(TM.TM_PSID) IN ({binds})")
                params.update(bparams)
            params["limit"] = n
            sql = f"SELECT * FROM (SELECT TRIM(TM.TM_GRSNO), TM.TM_DATE, TRIM(TM.TM_PSID), TRIM(TM.TM_NAME), TRIM(TM.TM_RSTP), TRIM(TD.TD_FORMAT), TRIM(TD.TD_SUBJ), TRIM(TD.TD_PATH), TRIM(DF.DF_NAME), NVL(DBMS_LOB.GETLENGTH(DF.DF_DATA), 0) FROM {tm} TM JOIN {td} TD ON TM.TM_SNO = TD.TD_SNO LEFT JOIN {df} DF ON TRIM(DF.DF_PATH) = TRIM(TD.TD_PATH) WHERE 1=1 {' '.join(clauses)} ORDER BY TM.TM_DATE DESC) WHERE ROWNUM <= :limit"
            return self._query_all(sql, params)
        # Sybase
        clauses: list[str] = []
        params: list[Any] = []
        if grsno:
            clauses.append("AND CONVERT(VARCHAR(64), TM.TM_GRSNO) LIKE ? ESCAPE '\\'")
            params.append(self._like_value(grsno))
        if subject:
            clauses.append("AND CONVERT(VARCHAR(4000), TD.TD_SUBJ) LIKE ? ESCAPE '\\'")
            params.append(self._like_value(subject))
        if days_ago:
            clauses.append("AND TM.TM_DATE >= DATEADD(day, -?, GETDATE())")
            params.append(int(days_ago))
        normalized_psids = self._normalize_psids(psids)
        if normalized_psids:
            placeholders = ",".join(["?"] * len(normalized_psids))
            clauses.append(f"AND CONVERT(VARCHAR(64), TM.TM_PSID) IN ({placeholders})")
            params.extend(normalized_psids)
        sql = (
            f"SELECT TOP {n} "
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
            f"WHERE 1=1 {' '.join(clauses)} "
            f"ORDER BY TM.TM_DATE DESC, TM.TM_SNO DESC, TD.TD_PATH"
        )
        return self._query_all(sql, params)

