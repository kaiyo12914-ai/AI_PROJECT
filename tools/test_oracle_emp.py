#!/usr/bin/env python
import argparse
import os
import sys
from typing import List


def _mask(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 4:
        return "*" * len(val)
    return val[:2] + "*" * (len(val) - 4) + val[-2:]


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "webproj.settings")
    try:
        import django

        django.setup()
    except Exception as exc:
        print(f"[ERR] django.setup failed: {exc}")
        sys.exit(2)


def _print_env() -> None:
    from django.conf import settings

    ora_host = getattr(settings, "ORA_HOST", "")
    ora_service = getattr(settings, "ORA_SERVICE_NAME", "")
    ora_user = getattr(settings, "ORA_USER", "")
    ora_pass = getattr(settings, "ORA_PASS", "")

    print("[ENV] ORACLE_ENABLED:", getattr(settings, "ORACLE_ENABLED", None))
    print("[ENV] ORACLE_EMP_ENABLED:", getattr(settings, "ORACLE_EMP_ENABLED", None))
    print("[ENV] EMP_NAME_LOOKUP (env):", os.getenv("EMP_NAME_LOOKUP"))
    print("[ENV] ORA_HOST:", ora_host)
    print("[ENV] ORA_SERVICE_NAME:", ora_service)
    print("[ENV] ORA_USER:", ora_user)
    print("[ENV] ORA_PASS (masked):", _mask(ora_pass))


def _lookup(emp_ids: List[str], refresh: bool) -> int:
    from webapps.portal.oracle_emp import get_emp_name, get_last_error, clear_cache

    if refresh:
        clear_cache()

    ok = True
    for emp_id in emp_ids:
        name = get_emp_name(emp_id, refresh=refresh)
        if name:
            print(f"[OK] {emp_id} => {name}")
        else:
            err = get_last_error()
            print(f"[FAIL] {emp_id} => empty (err={err})")
            ok = False
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Oracle EMP lookup (CT_EMPLOY)")
    parser.add_argument("emp_id", nargs="+", help="Employee ID(s) to lookup (CT_EMPLOY.IDNO)")
    parser.add_argument("--refresh", action="store_true", help="bypass cache / clear cache")
    parser.add_argument("--no-env", action="store_true", help="do not print env settings")
    args = parser.parse_args()

    _setup_django()
    if not args.no_env:
        _print_env()

    return _lookup(args.emp_id, refresh=args.refresh)


if __name__ == "__main__":
    raise SystemExit(main())
