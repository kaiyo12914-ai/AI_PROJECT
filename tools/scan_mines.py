# tools/scan_mines.py
# -*- coding: utf-8 -*-
"""
一鍵掃雷：掃描專案中會導致「反代 prefix / apiUrl」互相干擾的地雷點
- 不修改檔案（只報告）
- 輸出：終端機 + 可選寫出 report.json / report.md

用法：
  python tools/scan_mines.py --root H:\AI\AI_TOOLS
  python tools/scan_mines.py --root . --write-md --write-json

建議先掃來源，不掃 collectstatic 產物：
  預設會略過 staticfiles/、venv/、.git/、node_modules/ 等
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


# -----------------------------
# patterns (mines)
# -----------------------------
MINE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # hardcoded proxy prefix
    ("HARD_CODED_DJANGOAI", re.compile(r'["\']/djangoai\b', re.IGNORECASE)),
    ("DOUBLE_PREFIX_DJANGOAI", re.compile(r"/djangoai\s*/djangoai", re.IGNORECASE)),
    # legacy globals
    ("LEGACY_FORCE_SCRIPT_GLOBAL", re.compile(r"__FORCE_SCRIPT_NAME__", re.IGNORECASE)),
    ("LEGACY_PROXY_PREFIX_GLOBAL", re.compile(r"__PROXY_PREFIX__", re.IGNORECASE)),
    # custom apiUrl definitions
    ("APIURL_FUNCTION_DEF", re.compile(r"\bfunction\s+apiUrl\s*\(", re.IGNORECASE)),
    ("APIURL_ARROW_DEF", re.compile(r"\bconst\s+apiUrl\s*=\s*\(", re.IGNORECASE)),
    # typical bug: missing node, like apiUrl("api/...")
    ("APIURL_PATH_MISSING_NODE", re.compile(r'apiUrl\(\s*["\']api\/', re.IGNORECASE)),
    # typical bug: path includes /djangoai (should not)
    ("APIURL_PATH_HAS_PREFIX", re.compile(r'apiUrl\(\s*["\']\/djangoai\/', re.IGNORECASE)),
    # script_name not used at all (template)
    ("BODY_WITHOUT_BASEURL", re.compile(r"<body(?![^>]*data-base-url=)", re.IGNORECASE)),
    ("BASEURL_NOT_SCRIPTNAME", re.compile(r"data-base-url\s*=\s*\"(?!\{\{\s*request\.script_name\s*\}\})", re.IGNORECASE)),
]

# File types we scan
SCAN_EXT = {".js", ".html", ".htm", ".py", ".txt"}

# Directories to skip
SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    ".vscode",
    "venv",
    "venv3.12",
    "__pycache__",
    "node_modules",
    "staticfiles",   # collectstatic output
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
}

# Large file safeguard (bytes)
MAX_FILE_SIZE = 3 * 1024 * 1024  # 3MB


@dataclass
class Hit:
    file: str
    line: int
    col: int
    rule: str
    excerpt: str
    context: str


def iter_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        # prune skip dirs
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in SCAN_EXT:
                yield p


def read_text(p: Path) -> Optional[str]:
    try:
        if p.stat().st_size > MAX_FILE_SIZE:
            return None
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def make_context(lines: List[str], idx0: int, radius: int = 2) -> str:
    start = max(0, idx0 - radius)
    end = min(len(lines), idx0 + radius + 1)
    chunk = []
    for i in range(start, end):
        prefix = ">> " if i == idx0 else "   "
        chunk.append(f"{prefix}{i+1:4d}: {lines[i].rstrip()}")
    return "\n".join(chunk)


def scan_file(p: Path, root: Path) -> List[Hit]:
    text = read_text(p)
    if text is None:
        return []

    rel = str(p.relative_to(root)).replace("\\", "/")
    lines = text.splitlines()
    hits: List[Hit] = []

    for rule_name, pat in MINE_PATTERNS:
        # Special: BODY_WITHOUT_BASEURL should only apply to templates, not all files
        if rule_name in ("BODY_WITHOUT_BASEURL", "BASEURL_NOT_SCRIPTNAME"):
            if p.suffix.lower() not in (".html", ".htm"):
                continue

        for m in pat.finditer(text):
            # compute line/col
            before = text[: m.start()]
            line_no = before.count("\n") + 1
            col = (len(before) - before.rfind("\n")) if "\n" in before else (m.start() + 1)
            idx0 = line_no - 1
            excerpt = m.group(0)

            ctx = make_context(lines, idx0, radius=2) if 0 <= idx0 < len(lines) else ""

            hits.append(
                Hit(
                    file=rel,
                    line=line_no,
                    col=col,
                    rule=rule_name,
                    excerpt=excerpt,
                    context=ctx,
                )
            )

    return hits


def summarize(hits: List[Hit]) -> dict:
    by_rule = {}
    by_file = {}
    for h in hits:
        by_rule[h.rule] = by_rule.get(h.rule, 0) + 1
        by_file[h.file] = by_file.get(h.file, 0) + 1

    top_rules = sorted(by_rule.items(), key=lambda x: x[1], reverse=True)
    top_files = sorted(by_file.items(), key=lambda x: x[1], reverse=True)

    return {
        "total_hits": len(hits),
        "by_rule": top_rules,
        "by_file": top_files[:30],
    }


def to_markdown(report: dict) -> str:
    hits = report["hits"]
    summary = report["summary"]

    md = []
    md.append("# Proxy/API 掃雷報告\n")
    md.append(f"- 總命中：**{summary['total_hits']}**\n")
    md.append("## 規則命中統計\n")
    for rule, cnt in summary["by_rule"]:
        md.append(f"- `{rule}`: {cnt}")
    md.append("\n## 檔案命中 Top\n")
    for f, cnt in summary["by_file"]:
        md.append(f"- `{f}`: {cnt}")
    md.append("\n---\n")
    md.append("## 明細（檔案 / 行號 / 規則 / 片段）\n")

    for h in hits:
        md.append(f"### {h['file']}:{h['line']}  `{h['rule']}`")
        md.append(f"- excerpt: `{h['excerpt']}`\n")
        md.append("```text")
        md.append(h["context"])
        md.append("```\n")

    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="專案根目錄（預設 .）")
    ap.add_argument("--write-json", action="store_true", help="輸出 report_proxy_mines.json")
    ap.add_argument("--write-md", action="store_true", help="輸出 report_proxy_mines.md")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    all_hits: List[Hit] = []
    for p in iter_files(root):
        all_hits.extend(scan_file(p, root))

    # stable sort
    all_hits.sort(key=lambda h: (h.file, h.line, h.col, h.rule))

    report = {
        "root": str(root).replace("\\", "/"),
        "summary": summarize(all_hits),
        "hits": [
            {
                "file": h.file,
                "line": h.line,
                "col": h.col,
                "rule": h.rule,
                "excerpt": h.excerpt,
                "context": h.context,
            }
            for h in all_hits
        ],
    }

    # console summary
    print("==== Proxy/API 掃雷（只讀） ====")
    print(f"ROOT: {report['root']}")
    print(f"TOTAL HITS: {report['summary']['total_hits']}")
    print("\n-- By Rule --")
    for rule, cnt in report["summary"]["by_rule"]:
        print(f"{rule:28s} {cnt}")
    print("\n-- Top Files --")
    for f, cnt in report["summary"]["by_file"]:
        print(f"{cnt:4d}  {f}")

    if args.write_json:
        out_json = root / "report_proxy_mines.json"
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[OK] wrote {out_json}")

    if args.write_md:
        out_md = root / "report_proxy_mines.md"
        out_md.write_text(to_markdown(report), encoding="utf-8")
        print(f"\n[OK] wrote {out_md}")

    # exit code for CI usage
    # 0: clean, 2: has mines
    raise SystemExit(0 if report["summary"]["total_hits"] == 0 else 2)


if __name__ == "__main__":
    main()

# """
# 一鍵掃雷：掃描專案中會導致「反代 prefix / apiUrl」互相干擾的地雷點
# - 不修改檔案（只報告）
# - 輸出：終端機 + 可選寫出 report.json / report.md
# # python tools/scan_mines.py --root . --write-md --write-json