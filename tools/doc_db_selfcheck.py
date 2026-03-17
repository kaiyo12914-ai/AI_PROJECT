from __future__ import annotations

import argparse
import os

from webapps.doc.services.docService import docService


def main() -> int:
    ap = argparse.ArgumentParser(description="DOC Sybase self-check (print Chinese fields)")
    ap.add_argument("--grsno", default="1150000712", help="TM_GRSNO / EM_GRSNO")
    ap.add_argument("--login_user", default="", help="login user (fallback to DEV_LOGIN_USER)")
    args = ap.parse_args()

    login_user = (args.login_user or os.getenv("DEV_LOGIN_USER") or "").strip()
    if not login_user:
        print("missing login_user (set --login_user or DEV_LOGIN_USER)")
        return 2

    grsno = (args.grsno or "").strip()
    if not grsno:
        print("missing grsno")
        return 2

    svc = docService()
    rows = svc.lookup_incoming(login_user, grsno)
    print(f"rows={len(rows)} grsno={grsno} login_user={login_user}")
    if not rows:
        return 0

    r = rows[0]
    try:
        print("EM_GRSNO:", r[0])
        print("EM_PSID:", r[1])
        print("TD_SUBJ:", r[2])
        print("EF_ID:", r[3])
        print("EF_NAME:", r[4])
        print("EF_PAGE:", r[5] if len(r) > 5 else "")
    except Exception as e:
        print("row access error:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
