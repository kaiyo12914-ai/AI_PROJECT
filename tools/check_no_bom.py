#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check text files for UTF-8 BOM. Exit non-zero if any are found.

Usage:
  python tools/check_no_bom.py
  python tools/check_no_bom.py --root h:\\AI\\Django\\webapps
"""

from __future__ import annotations

import argparse
from pathlib import Path


TEXT_EXTS = {
    ".py",
    ".js",
    ".css",
    ".html",
    ".md",
    ".txt",
    ".json",
    ".ini",
    ".yml",
    ".yaml",
}


def find_bom_files(root: Path) -> list[Path]:
    hits: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if data.startswith(b"\xef\xbb\xbf"):
            hits.append(path)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Check UTF-8 BOM in text files.")
    parser.add_argument("--root", default="webapps", help="Root directory to scan.")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"[ERR] root not found: {root}")
        return 2

    hits = find_bom_files(root)
    if hits:
        print("[ERR] UTF-8 BOM detected:")
        for p in hits:
            print(p)
        return 1

    print("[OK] no UTF-8 BOM found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
