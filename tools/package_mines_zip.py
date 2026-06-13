# tools/package_mines_zip.py
# -*- coding: utf-8 -*-
"""
一鍵打包：把掃雷命中的檔案，依原目錄結構打包成 ZIP
- 讀取 mine_files.txt（每行一個相對路徑）
- ZIP 內附：
  - MANIFEST.txt：檔案清單（含 size/mtime）
  - AI_PROMPT.txt：可直接貼給 AI 的「依專案規範」修正提示詞（由外部檔讀入，避免三引號地雷）
  - docs/專案規範.docx（若提供 --spec）
用法：
  python tools/package_mines_zip.py --root . --list tools/mine_files.txt --out mines_bundle.zip --spec ./tools/專案規範.docx
"""

from __future__ import annotations

import argparse
import os
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class FileItem:
    rel: str
    abs: Path
    size: int
    mtime: float


def _norm_rel(s: str) -> str:
    s = (s or "").strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    # prevent absolute / drive letters
    s = s.lstrip("/")
    # collapse repeated slashes
    while "//" in s:
        s = s.replace("//", "/")
    return s


def _read_list(list_path: Path) -> List[str]:
    if not list_path.exists():
        raise FileNotFoundError(f"List file not found: {list_path}")

    lines: List[str] = []
    raw = list_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for ln in raw:
        s = (ln or "").strip()
        if not s or s.startswith("#"):
            continue
        s = _norm_rel(s)
        if not s:
            continue
        lines.append(s)

    # de-dup preserving order
    seen = set()
    out: List[str] = []
    for x in lines:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _stat_file(root: Path, rel: str) -> Tuple[FileItem | None, str]:
    rel2 = _norm_rel(rel)
    if not rel2:
        return None, f"ERR : empty rel"

    p = (root / rel2).resolve()
    try:
        if not p.exists() or not p.is_file():
            return None, f"MISS: {rel2}"
        st = p.stat()
        return FileItem(rel=rel2, abs=p, size=int(st.st_size), mtime=float(st.st_mtime)), ""
    except Exception as e:
        return None, f"ERR : {rel2} ({type(e).__name__}: {e})"


def _fmt_ts(ts: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return str(ts)


def _build_manifest(items: List[FileItem], misses: List[str], root: Path) -> str:
    lines: List[str] = []
    lines.append("=== MINES BUNDLE MANIFEST ===")
    lines.append(f"ROOT: {str(root).replace(os.sep, '/')}")
    lines.append(f"TOTAL_FILES: {len(items)}")
    lines.append(f"TOTAL_MISSING: {len(misses)}")
    lines.append("")
    lines.append("-- FILES (rel | size | mtime) --")
    for it in sorted(items, key=lambda x: x.rel):
        lines.append(f"{it.rel} | {it.size} | {_fmt_ts(it.mtime)}")
    if misses:
        lines.append("")
        lines.append("-- MISSING/ERROR --")
        lines.extend(misses)
    lines.append("")
    return "\n".join(lines)


def load_ai_prompt(prompt_path: Path) -> str:
    try:
        return prompt_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        raise RuntimeError(f"Failed to read AI prompt: {prompt_path}") from e


def _zip_write_file(zf: zipfile.ZipFile, *, arcname: str, src: Path) -> None:
    """
    寫入 ZIP，保護：不允許 arcname 為絕對路徑或含 ..（避免 zip slip）
    """
    arc = _norm_rel(arcname)
    if not arc:
        raise ValueError("arcname is empty")
    if ".." in arc.split("/"):
        raise ValueError(f"unsafe arcname (..): {arc}")
    zf.write(src, arc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="專案根目錄（預設 .）")
    ap.add_argument("--list", required=True, help="檔案清單（每行一個相對路徑）")
    ap.add_argument("--out", required=True, help="輸出 zip 檔名（例如 mines_bundle.zip）")
    ap.add_argument("--spec", default="", help="專案規範 docx 路徑（可省略）")
    ap.add_argument(
        "--prompt",
        default="tools/AI_PROMPT.txt",
        help="AI_PROMPT.txt 路徑（預設 tools/AI_PROMPT.txt；建議放外部檔避免三引號地雷）",
    )
    ap.add_argument("--include-list", action="store_true", help="把 --list 也打包進 ZIP（預設不打包）")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    list_path = (root / args.list).resolve() if not Path(args.list).is_absolute() else Path(args.list).resolve()
    out_path = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out).resolve()

    prompt_path = (root / args.prompt).resolve() if not Path(args.prompt).is_absolute() else Path(args.prompt).resolve()
    if not prompt_path.exists():
        raise SystemExit(f"AI prompt file not found: {prompt_path}\n請建立 tools/AI_PROMPT.txt（或用 --prompt 指定）")

    rels = _read_list(list_path)

    items: List[FileItem] = []
    misses: List[str] = []

    for rel in rels:
        it, err = _stat_file(root, rel)
        if it:
            items.append(it)
        else:
            misses.append(err)

    manifest = _build_manifest(items, misses, root)
    ai_prompt = load_ai_prompt(prompt_path)

    spec_src: Path | None = None
    if (args.spec or "").strip():
        sp = Path(args.spec)
        spec_src = (root / sp).resolve() if not sp.is_absolute() else sp.resolve()
        if not spec_src.exists():
            misses.append(f"MISS: spec not found: {spec_src}")
            spec_src = None

    # build zip
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1) payload files
        for it in items:
            _zip_write_file(zf, arcname=it.rel, src=it.abs)

        # 2) manifest + ai prompt
        zf.writestr("MANIFEST.txt", manifest)
        zf.writestr("AI_PROMPT.txt", ai_prompt)

        # 3) optional: include list file
        if args.include_list:
            _zip_write_file(zf, arcname="mine_files.txt", src=list_path)

        # 4) optional: spec docx
        if spec_src:
            # 放 docs/ 下，保留原檔名（中文可）
            zf.write(spec_src, f"docs/{spec_src.name}")

    # console output
    print("==== MINES BUNDLE PACKED ====")
    print(f"ROOT: {str(root).replace(os.sep, '/')}")
    print(f"LIST: {str(list_path).replace(os.sep, '/')}")
    print(f"OUT : {str(out_path).replace(os.sep, '/')}")
    print(f"FILES_PACKED: {len(items)}")
    print(f"MISSING/ERR: {len(misses)}")
    if spec_src:
        print(f"SPEC: {spec_src.name} -> docs/{spec_src.name}")
    print("OK")


if __name__ == "__main__":
    main()
