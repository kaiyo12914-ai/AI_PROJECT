# tools/export_URLS.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

import django
from django.urls import URLPattern, URLResolver, get_resolver


def _project_root() -> Path:
    # tools/ 的上一層通常就是專案根目錄
    return Path(__file__).resolve().parents[1]


def _read_settings_module_from_manage_py(root: Path) -> str:
    """
    從 manage.py 解析 DJANGO_SETTINGS_MODULE，避免手動填錯（例如 webproj）
    """
    manage_py = root / "manage.py"
    if not manage_py.exists():
        raise SystemExit(f"manage.py not found under root: {root}")

    text = manage_py.read_text(encoding="utf-8", errors="ignore")

    # 支援單引號/雙引號
    m = re.search(
        r"os\.environ\.setdefault\(\s*['\"]DJANGO_SETTINGS_MODULE['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)",
        text,
    )
    if not m:
        raise SystemExit("Cannot find DJANGO_SETTINGS_MODULE in manage.py (os.environ.setdefault(...))")
    return m.group(1).strip()


def _init_django(root: Path, settings_module: Optional[str] = None) -> str:
    """
    初始化 Django settings
    - 將 root 加入 sys.path
    - 設定 DJANGO_SETTINGS_MODULE（若未指定，從 manage.py 讀）
    """
    sys.path.insert(0, str(root))

    sm = settings_module or _read_settings_module_from_manage_py(root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", sm)

    django.setup()
    return sm


def _walk_urls(patterns, prefix: str = "", out: Optional[List[str]] = None) -> List[str]:
    """
    遞迴列出所有 URL
    輸出格式：
      <pattern> | name=<name> | view=<callback>
    """
    if out is None:
        out = []

    for p in patterns:
        if isinstance(p, URLPattern):
            pattern = f"{prefix}{p.pattern}"
            name = p.name or ""
            callback = getattr(p.callback, "__qualname__", str(p.callback))
            module = getattr(p.callback, "__module__", "")
            view = f"{module}.{callback}" if module else callback
            out.append(f"{pattern} | name={name} | view={view}")
        elif isinstance(p, URLResolver):
            _walk_urls(p.url_patterns, prefix + str(p.pattern), out)

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root",
        default="",
        help="專案根目錄（預設自動判斷 tools/ 上一層）",
    )
    ap.add_argument(
        "--settings",
        default="",
        help="手動指定 DJANGO_SETTINGS_MODULE（預設從 manage.py 自動解析）",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else _project_root()
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    settings_module = args.settings.strip() or None
    sm = _init_django(root, settings_module)

    lines = _walk_urls(get_resolver().url_patterns)
    lines_sorted = sorted(lines)

    # 固定輸出位置：<專案根>/TOOLS/Django_Urls.txt
    out_path = (root / "TOOLS" / "Django_Urls.txt").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    header = [
        "=== DJANGO URLS EXPORT ===",
        f"ROOT: {str(root).replace(os.sep, '/')}",
        f"DJANGO_SETTINGS_MODULE: {sm}",
        f"TOTAL: {len(lines_sorted)}",
        "",
    ]
    content = "\n".join(header + lines_sorted) + "\n"

    out_path.write_text(content, encoding="utf-8")

    print("OK")
    print(f"ROOT: {str(root).replace(os.sep, '/')}")
    print(f"DJANGO_SETTINGS_MODULE: {sm}")
    print(f"OUT:  {str(out_path).replace(os.sep, '/')}")
    print(f"TOTAL: {len(lines_sorted)}")


if __name__ == "__main__":
    main()


# python tools\export_URLS.py