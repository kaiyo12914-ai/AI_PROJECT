# webapps/rag_oracle/oracle_conn.py
from __future__ import annotations

from django.conf import settings
import oracledb


def get_conn():
    host = settings.ORA_HOST
    port = int(getattr(settings, "ORA_PORT", 1521))
    svc = settings.ORA_SERVICE_NAME
    user = settings.ORA_USER
    pwd = settings.ORA_PASS

    dsn = oracledb.makedsn(host=host, port=port, service_name=svc)
    return oracledb.connect(user=user, password=pwd, dsn=dsn)
