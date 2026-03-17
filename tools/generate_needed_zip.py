# tools/package_needed_zip.py
# -*- coding: utf-8 -*-
"""
一鍵打包 needed_code.txt 指定的程式碼為 ZIP（保留原目錄結構）
- 讀取 needed_code.txt（每行可為「相對路徑」或「絕對路徑」；可包含目錄）
- 只打包指定副檔名（預設 .py .html .js .css）
- ZIP 內附：
  - MANIFEST.txt：檔案清單（含 size/mtime）
  - AI_PROMPT.txt：由外部檔讀入（避免三引號地雷）
  - docs/專案規範.docx（若提供 --spec）
  - TOOLS/DJANGO_URLS.TXT（若提供 --urls 且檔案存在；預設會找 TOOLS/DJANGO_URLS.TXT）
- OUT 會自動加時間戳：<stem><MMDD>_<HH>_<MM>.zip
  例如：needed_code0127_14_35.zip

用法：
  python tools/package_needed_zip.py --root . --needs webproj/needed_code.txt --out needed_code.zip --spec 專案規範.docx
  python tools/package_needed_zip.py --root H:\\AI\\Django --needs tools\\needed_code.txt --out tools\\needed_code.zip --spec H:\\AI\\Django\\tools\\專案規範.docx

加打包路由檔（可選）：
  python tools/package_needed_zip.py --root H:\\AI\\Django --needs tools\\needed_code.txt --out tools\\needed_code.zip --urls TOOLS\\DJANGO_URLS.TXT

建議：
  - 將你的 AI 修正提示詞放在 tools/AI_PROMPT.txt（或用 --prompt 指定）
"""

from __future__ import annotations

import argparse
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple


DEFAULT_EXTS = (".py", ".html", ".js", ".css")


@dataclass
class FileItem:
    rel: str
    abs: Path
    size: int
    mtime: float


def _norm_slash(s: str) -> str:
    return (s or "").strip().replace("\\", "/")


def _norm_rel(s: str) -> str:
    s = _norm_slash(s)
    while s.startswith("./"):
        s = s[2:]
    s = s.lstrip("/")  # prevent absolute in zip
    while "//" in s:
        s = s.replace("//", "/")
    return s


def _fmt_ts(ts: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return str(ts)


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


def _resolve_entry(root: Path, entry: str) -> Path:
    """
    needed_code.txt 每行可以是：
      - 相對於 root 的路徑
      - 絕對路徑
    """
    s = (entry or "").strip()
    if not s:
        raise ValueError("empty entry")
    p = Path(s)
    if p.is_absolute():
        return p.resolve()
    return (root / _norm_rel(s)).resolve()


def _read_needs(needs_path: Path) -> List[str]:
    if not needs_path.exists():
        raise FileNotFoundError(f"needs file not found: {needs_path}")
    lines: List[str] = []
    raw = needs_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for ln in raw:
        s = (ln or "").strip()
        if not s or s.startswith("#"):
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


def _collect_files_from_dir(d: Path, exts: Tuple[str, ...]) -> Iterable[Path]:
    # 遞迴找檔，排序穩定
    for p in sorted(d.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def _to_rel_under_root(root: Path, p: Path) -> str:
    """
    將檔案轉成「相對於 root」的 zip 路徑
    - 若檔案不在 root 底下：放入 external/ 下，避免破壞專案結構也避免跳出 root
    """
    try:
        rel = p.resolve().relative_to(root.resolve())
        return _norm_rel(rel.as_posix())
    except Exception:
        # 檔案在 root 外：仍可打包，但隔離到 external/
        return _norm_rel("external/" + p.name)


def _stat_file(root: Path, p: Path) -> Tuple[FileItem | None, str]:
    try:
        if not p.exists() or not p.is_file():
            return None, f"MISS: {str(p).replace(os.sep, '/')}"
        st = p.stat()
        rel = _to_rel_under_root(root, p)
        return FileItem(rel=rel, abs=p, size=int(st.st_size), mtime=float(st.st_mtime)), ""
    except Exception as e:
        return None, f"ERR : {str(p).replace(os.sep, '/')} ({type(e).__name__}: {e})"


def _build_manifest(items: List[FileItem], misses: List[str], root: Path, needs_file: Path) -> str:
    lines: List[str] = []
    lines.append("=== NEEDED CODE MANIFEST ===")
    lines.append(f"ROOT: {str(root).replace(os.sep, '/')}")
    lines.append(f"NEEDS_FILE: {str(needs_file).replace(os.sep, '/')}")
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


def _out_with_timestamp(out_file: Path) -> Path:
    """
    將 --out 檔名自動加上 MMDD_HH_MM，例如：
      tools/needed_code.zip -> tools/needed_code0127_14_35.zip
    """
    now = datetime.now()
    ts = now.strftime("%m%d_%H_%M")
    stem = out_file.stem
    suffix = out_file.suffix or ".zip"
    new_name = f"{stem}{ts}{suffix}"
    return out_file.with_name(new_name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="專案根目錄（預設 .）")
    ap.add_argument("--needs", default="webproj/needed_code.txt", help="needed_code.txt 路徑（預設 webproj/needed_code.txt）")
    ap.add_argument("--out", default="needed_code.zip", help="輸出 zip 檔名（預設 needed_code.zip；會自動加時間戳）")
    ap.add_argument("--spec", default="", help="專案規範 docx 路徑（可省略）")
    ap.add_argument(
        "--prompt",
        default="tools/AI_PROMPT.txt",
        help="AI_PROMPT.txt 路徑（預設 tools/AI_PROMPT.txt；建議放外部檔避免三引號地雷）",
    )
    ap.add_argument(
        "--urls",
        default="TOOLS/DJANGO_URLS.TXT",
        help="要額外打包的 Django 路由清單檔（預設 TOOLS/DJANGO_URLS.TXT；留空則不處理）",
    )
    ap.add_argument("--include-list", action="store_true", help="把 needed_code.txt 也打包進 ZIP（預設不打包）")
    ap.add_argument(
        "--ext",
        default=",".join(DEFAULT_EXTS),
        help="允許打包的副檔名（逗號分隔，預設 .py,.html,.js,.css）",
    )
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    needs_file = Path(args.needs)
    needs_path = (root / needs_file).resolve() if not needs_file.is_absolute() else needs_file.resolve()
    if not needs_path.exists():
        raise SystemExit(f"needs file not found: {needs_path}")

    # OUT: 自動加時間戳
    out_file = Path(args.out)
    out_file_ts = _out_with_timestamp(out_file)
    out_path = (root / out_file_ts).resolve() if not out_file_ts.is_absolute() else out_file_ts.resolve()

    prompt_file = Path(args.prompt)
    prompt_path = (root / prompt_file).resolve() if not prompt_file.is_absolute() else prompt_file.resolve()
    if not prompt_path.exists():
        raise SystemExit(f"AI prompt file not found: {prompt_path}\n請建立 tools/AI_PROMPT.txt（或用 --prompt 指定）")

    exts = tuple([e.strip().lower() for e in (args.ext or "").split(",") if e.strip()])
    if not exts:
        raise SystemExit("No valid extensions provided via --ext")

    entries = _read_needs(needs_path)

    items: List[FileItem] = []
    misses: List[str] = []
    seen_abs = set()

    # 收集檔案
    for entry in entries:
        try:
            p = _resolve_entry(root, entry)
        except Exception as e:
            misses.append(f"ERR : {entry} ({type(e).__name__}: {e})")
            continue

        if not p.exists():
            misses.append(f"MISS: {str(p).replace(os.sep, '/')}")
            continue

        if p.is_file():
            if p.suffix.lower() not in exts:
                misses.append(f"SKIP: ext not allowed: {str(p).replace(os.sep, '/')}")
                continue
            if str(p) in seen_abs:
                continue
            seen_abs.add(str(p))
            it, err = _stat_file(root, p)
            if it:
                items.append(it)
            else:
                misses.append(err)
        else:
            # 目錄：遞迴收集
            for fp in _collect_files_from_dir(p, exts):
                if str(fp) in seen_abs:
                    continue
                seen_abs.add(str(fp))
                it, err = _stat_file(root, fp)
                if it:
                    items.append(it)
                else:
                    misses.append(err)

    ai_prompt = load_ai_prompt(prompt_path)

    # optional: spec
    spec_src: Path | None = None
    if (args.spec or "").strip():
        sp = Path(args.spec)
        spec_src = (root / sp).resolve() if not sp.is_absolute() else sp.resolve()
        if not spec_src.exists():
            misses.append(f"MISS: spec not found: {spec_src}")
            spec_src = None

    # optional: urls export file
    urls_src: Path | None = None
    if (args.urls or "").strip():
        up = Path(args.urls)
        urls_src = (root / up).resolve() if not up.is_absolute() else up.resolve()
        if not urls_src.exists() or not urls_src.is_file():
            misses.append(f"MISS: urls file not found: {urls_src}")
            urls_src = None

    manifest = _build_manifest(items, misses, root, needs_path)

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

        # 3) optional: include list
        if args.include_list:
            _zip_write_file(zf, arcname="needed_code.txt", src=needs_path)

        # 4) optional: spec docx
        if spec_src:
            zf.write(spec_src, f"docs/{spec_src.name}")

        # 5) optional: urls export txt
        if urls_src:
            # 放在 TOOLS/ 下，固定檔名 DJANGO_URLS.TXT（與 export_URLS.py 一致）
            zf.write(urls_src, "TOOLS/DJANGO_URLS.TXT")

    # console output
    print("==== NEEDED CODE PACKED ====")
    print(f"ROOT : {str(root).replace(os.sep, '/')}")
    print(f"NEEDS: {str(needs_path).replace(os.sep, '/')}")
    print(f"OUT  : {str(out_path).replace(os.sep, '/')}")
    print(f"EXTS : {', '.join(exts)}")
    print(f"FILES_PACKED: {len(items)}")
    print(f"MISSING/OTHER: {len(misses)}")
    if urls_src:
        print("URLS: TOOLS/DJANGO_URLS.TXT included")
    if spec_src:
        print(f"SPEC: {spec_src.name} -> docs/{spec_src.name}")
    print("OK")


if __name__ == "__main__":
    main()


# 將 needed_code.txt 指定的程式碼打包為 ZIP
# python tools/generate_needed_zip.py --root H:\\AI\\Django --needs tools\\needed_code.txt --out tools\\needed_code.zip --spec H:\\AI\\Django\\tools\\專案規範.docx