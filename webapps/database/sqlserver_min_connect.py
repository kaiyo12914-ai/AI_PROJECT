#!/usr/bin/env python
"""
Minimal SQL Server connectivity check.

Usage:
  python webapps/database/sqlserver_min_connect.py
  python webapps/database/sqlserver_min_connect.py --query "SELECT @@VERSION"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def _clean_value(v: str) -> str:
    v = (v or "").strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1].strip()
    return v


def _parse_kv_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().upper()
        if not re.match(r"^[A-Z0-9_]+$", key):
            continue
        out[key] = _clean_value(value)
    return out


def _read_text_if_exists(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        pass
    return ""


def _load_file_config(md_path_arg: str) -> dict[str, str]:
    # Project root is expected at .../AI_TOOLS
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    md_path = Path(md_path_arg).expanduser() if md_path_arg else None

    if md_path is None:
        md_path_env = (os.getenv("DB_FACTORY_MD_PATH") or "").strip()
        md_path = Path(md_path_env).expanduser() if md_path_env else (root / "DB_FACTORY.MD")

    cfg: dict[str, str] = {}
    cfg.update(_parse_kv_text(_read_text_if_exists(env_path)))
    # DB_FACTORY.MD overrides .env (same as project rule).
    cfg.update(_parse_kv_text(_read_text_if_exists(md_path)))
    cfg["__ENV_PATH__"] = str(env_path)
    cfg["__MD_PATH__"] = str(md_path)
    return cfg


def _pick(name: str, file_cfg: dict[str, str], default: str = "") -> str:
    return (os.getenv(name) or file_cfg.get(name) or default).strip()


def _to_int(s: str, default: int) -> int:
    try:
        return int((s or "").strip())
    except Exception:
        return default


def _build_conn_str(args: argparse.Namespace) -> str:
    # DSN mode first (if provided).
    if args.dsn:
        parts = [f"DSN={args.dsn}"]
        if args.user:
            parts.append(f"UID={args.user}")
        if args.password:
            parts.append(f"PWD={args.password}")
        if args.database:
            parts.append(f"DATABASE={args.database}")
        return ";".join(parts)

    server = args.host
    if "\\" in server:
        # Host already includes instance (host\instance).
        server = server.replace("\\\\", "\\")
    elif args.instance:
        server = f"{args.host}\\{args.instance}"
    elif args.port:
        server = f"{args.host},{args.port}"

    parts = [
        f"DRIVER={{{args.driver}}}",
        f"SERVER={server}",
        f"DATABASE={args.database}",
    ]
    if args.user:
        parts.append(f"UID={args.user}")
        parts.append(f"PWD={args.password}")
    else:
        # Windows integrated authentication fallback.
        parts.append("Trusted_Connection=yes")
    return ";".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal SQL Server connection test")
    parser.add_argument("--md-path", default="", help="Path to DB_FACTORY.MD (optional)")
    parser.add_argument("--dsn", default="")
    parser.add_argument("--host", default="")
    parser.add_argument("--instance", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--database", default="")
    parser.add_argument("--user", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--driver", default="")
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--query", default="SELECT 1 AS ok")
    args = parser.parse_args()

    file_cfg = _load_file_config(args.md_path)
    args.dsn = args.dsn or _pick("SQL_SERVER_DSN", file_cfg)
    args.host = args.host or _pick("SQL_SERVER_HOST", file_cfg, "127.0.0.1")
    args.instance = args.instance or _pick("SQL_SERVER_INSTANCE", file_cfg)
    args.port = args.port or _to_int(_pick("SQL_SERVER_PORT", file_cfg, "1433"), 1433)
    args.database = args.database or _pick("SQL_SERVER_DB", file_cfg, "master")
    args.user = args.user or _pick("SQL_SERVER_USER", file_cfg)
    args.password = args.password or _pick("SQL_SERVER_PASS", file_cfg)
    args.driver = args.driver or _pick("SQL_SERVER_DRIVER", file_cfg, "ODBC Driver 17 for SQL Server")
    args.timeout = args.timeout or _to_int(_pick("SQLSERVER_CONNECT_TIMEOUT", file_cfg, "10"), 10)

    try:
        import pyodbc  # type: ignore
    except Exception:
        print("ERROR: pyodbc is not installed. Run: pip install pyodbc")
        return 2

    conn_str = _build_conn_str(args)
    print("Connecting to SQL Server...")
    print(f"Driver={args.driver} Database={args.database} Host={args.host}")
    print(f"Config source: .env={file_cfg.get('__ENV_PATH__')} DB_FACTORY.MD={file_cfg.get('__MD_PATH__')}")

    try:
        with pyodbc.connect(conn_str, timeout=args.timeout, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(args.query)
                row = cur.fetchone()
        print("SUCCESS: connection and query executed.")
        print(f"Result: {row}")
        return 0
    except Exception as e:
        print("FAILED: SQL Server connection test failed.")
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
