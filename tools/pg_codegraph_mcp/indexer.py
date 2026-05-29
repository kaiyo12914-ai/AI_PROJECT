from __future__ import annotations

import ast
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .db import ensure_schema


SOURCE_SUFFIXES = {".py": "python", ".js": "javascript", ".mjs": "javascript"}
SKIP_DIRS = {
    ".git",
    ".codegraph",
    ".pytest_cache",
    "__pycache__",
    "_template_checks",
    "chroma",
    "export_out",
    "no_use",
    "ref",
    "venv",
    "node_modules",
    "staticfiles",
    "media",
    "open-notebook-main",
    "whispercpp",
}


@dataclass
class SymbolRecord:
    name: str
    qualname: str
    kind: str
    line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    code: str = ""
    calls: list[tuple[str, int]] = field(default_factory=list)
    imports: list[tuple[str, int]] = field(default_factory=list)
    references: list[tuple[str, int]] = field(default_factory=list)
    extends: list[tuple[str, int]] = field(default_factory=list)
    instantiates: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class ExtractResult:
    symbols: list[SymbolRecord] = field(default_factory=list)


def _iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        base = Path(dirpath)
        for filename in filenames:
            p = base / filename
            rel = p.relative_to(root).as_posix()
            if "/vendor/" in rel:
                continue
            if p.suffix.lower() in SOURCE_SUFFIXES:
                files.append(p)
    return sorted(files)


def _line_at(source: str, line: int) -> str:
    lines = source.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return ""


def _signature(node: ast.AST) -> str:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    args = [a.arg for a in node.args.posonlyargs + node.args.args]
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    args.extend(a.arg for a in node.args.kwonlyargs)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return f"{node.name}({', '.join(args)})"


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        if name.endswith(".as_view"):
            return name[: -len(".as_view")]
        return name
    return ""


class PythonExtractor(ast.NodeVisitor):
    def __init__(self, source: str, module_prefix: str = "") -> None:
        self.source = source
        self.scope: list[str] = [module_prefix] if module_prefix else []
        self.class_depth = 0
        self.function_depth = 0
        self.symbols: list[SymbolRecord] = []
        self.current_symbol: SymbolRecord | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        symbol = self._add_symbol(node, "class")
        for base in node.bases:
            name = _call_name(base)
            if name:
                symbol.extends.append((name, getattr(base, "lineno", node.lineno)))
        self.scope.append(node.name)
        self.class_depth += 1
        self.generic_visit(node)
        self.class_depth -= 1
        self.scope.pop()

    def visit_Import(self, node: ast.Import) -> Any:
        if self.function_depth > 0:
            self.generic_visit(node)
            return
        for alias in node.names:
            symbol = self._add_light_symbol(alias.asname or alias.name, "import", node.lineno, node.lineno, _line_at(self.source, node.lineno))
            symbol.imports.append((alias.name, node.lineno))
            if self.current_symbol is not None:
                self.current_symbol.imports.append((alias.name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        if self.function_depth > 0:
            self.generic_visit(node)
            return
        module = "." * int(node.level or 0) + (node.module or "")
        if module == "__future__":
            self.generic_visit(node)
            return
        imported = ",".join(alias.name for alias in node.names)
        name = module or imported
        target = f"{module}.{imported}".strip(".")
        symbol = self._add_light_symbol(name, "import", node.lineno, node.lineno, _line_at(self.source, node.lineno))
        symbol.imports.append((target, node.lineno))
        if self.current_symbol is not None:
            self.current_symbol.imports.append((target, node.lineno))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        for target in node.targets:
            self._record_assignment(target, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        self._record_assignment(node.target, node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._visit_function(node, "function")

    def visit_Call(self, node: ast.Call) -> Any:
        call_name = _call_name(node.func)
        if call_name in {"path", "re_path"} and node.args and isinstance(node.args[0], ast.Constant):
            route = str(node.args[0].value)
            if not route:
                self.generic_visit(node)
                return
            route_symbol = self._add_light_symbol(route, "route", getattr(node, "lineno", 1), getattr(node, "lineno", 1), ast.get_source_segment(self.source, node) or "")
            if len(node.args) > 1:
                view_name = _call_name(node.args[1])
                if view_name:
                    route_symbol.references.append((view_name, getattr(node.args[1], "lineno", getattr(node, "lineno", 1))))
            self.generic_visit(node)
            return
        if self.current_symbol is not None:
            name = call_name
            if name:
                self.current_symbol.calls.append((name, getattr(node, "lineno", self.current_symbol.line)))
                short_name = name.rsplit(".", 1)[-1]
                if short_name[:1].isupper():
                    self.current_symbol.instantiates.append((name, getattr(node, "lineno", self.current_symbol.line)))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> Any:
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        if self.class_depth > 0:
            kind = "method"
        symbol = self._add_symbol(node, kind)
        self.scope.append(node.name)
        previous = self.current_symbol
        self.current_symbol = symbol
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1
        self.current_symbol = previous
        self.scope.pop()

    def _add_symbol(self, node: ast.AST, kind: str) -> SymbolRecord:
        name = getattr(node, "name")
        qualname = ".".join(self.scope + [name])
        line = int(getattr(node, "lineno", 1))
        end_line = int(getattr(node, "end_lineno", line))
        code = ast.get_source_segment(self.source, node) or ""
        docstring = ast.get_docstring(node) if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else ""
        symbol = SymbolRecord(
            name=name,
            qualname=qualname,
            kind=kind,
            line=line,
            end_line=end_line,
            signature=_signature(node),
            docstring=docstring or "",
            code=code,
        )
        self.symbols.append(symbol)
        return symbol

    def _add_light_symbol(self, name: str, kind: str, line: int, end_line: int, code: str) -> SymbolRecord:
        qualname = ".".join(self.scope + [name])
        symbol = SymbolRecord(
            name=name,
            qualname=qualname,
            kind=kind,
            line=line,
            end_line=end_line,
            code=code,
        )
        self.symbols.append(symbol)
        return symbol

    def _record_assignment(self, target: ast.AST, node: ast.AST) -> None:
        if self.function_depth > 0 or self.class_depth > 0:
            return
        names: list[str] = []
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.extend(elt.id for elt in target.elts if isinstance(elt, ast.Name))
        for name in names:
            self._add_light_symbol(name, "variable", getattr(node, "lineno", 1), getattr(node, "end_lineno", getattr(node, "lineno", 1)), ast.get_source_segment(self.source, node) or "")


def extract_python(source: str, module_prefix: str = "") -> list[SymbolRecord]:
    tree = ast.parse(source)
    extractor = PythonExtractor(source, module_prefix=module_prefix)
    extractor.visit(tree)
    return extractor.symbols


_JS_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)|"
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>|"
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*function\s*\(([^)]*)\)"
)
_JS_CLASS_RE = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)(?:\s+extends\s+([A-Za-z_$][\w$.]*))?")
_JS_IMPORT_RE = re.compile(r"^\s*import\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]")
_JS_VAR_RE = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)")
_JS_CALL_RE = re.compile(r"\b([A-Za-z_$][\w$.]*)\s*\(")
_JS_ROUTE_RE = re.compile(r"\b(?:fetch|apiurl|path)\s*\(\s*['\"]([^'\"]+)['\"]")


def _is_wrapped_iife(source: str) -> bool:
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("/*") or line.startswith("*"):
            continue
        return (
            line.startswith("(function")
            or line.startswith("(async function")
            or line.startswith("(() =>")
            or line.startswith("document.addEventListener(")
        )
    return False


def _extract_javascript_top_level_values(source: str, module_prefix: str = "") -> list[SymbolRecord]:
    symbols: list[SymbolRecord] = []
    global_depth = 0
    for idx, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        line_depth = global_depth
        var_match = _JS_VAR_RE.match(line)
        if var_match and line_depth == 0 and "=>" not in line and "function" not in line:
            name = var_match.group(1)
            kind = "constant" if line.lstrip().startswith("const ") or f"const {name}" in line else "variable"
            symbols.append(
                SymbolRecord(
                    name=name,
                    qualname=".".join(part for part in [module_prefix, name] if part),
                    kind=kind,
                    line=idx,
                    end_line=idx,
                    code=stripped,
                )
            )
        global_depth += line.count("{") - line.count("}")
    return symbols


def extract_javascript(source: str, module_prefix: str = "") -> list[SymbolRecord]:
    if _is_wrapped_iife(source):
        return _extract_javascript_top_level_values(source, module_prefix=module_prefix)
    symbols: list[SymbolRecord] = []
    lines = source.splitlines()
    active_function: SymbolRecord | None = None
    brace_depth = 0
    global_depth = 0

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        line_depth = global_depth
        class_match = _JS_CLASS_RE.match(line)
        if class_match:
            name = class_match.group(1)
            extends = class_match.group(2)
            symbol = SymbolRecord(
                name=name,
                qualname=".".join(part for part in [module_prefix, name] if part),
                kind="class",
                line=idx,
                end_line=idx,
                code=stripped,
            )
            if extends:
                symbol.extends.append((extends, idx))
            symbols.append(symbol)
            continue

        fn_match = _JS_FUNCTION_RE.match(line)
        if fn_match and (fn_match.group(1) or line_depth == 0):
            name = fn_match.group(1) or fn_match.group(3) or fn_match.group(5)
            args = fn_match.group(2) or fn_match.group(4) or fn_match.group(6) or ""
            symbol = SymbolRecord(
                name=name,
                qualname=".".join(part for part in [module_prefix, name] if part),
                kind="function",
                line=idx,
                end_line=idx,
                signature=f"{name}({args.strip()})",
                code=stripped,
            )
            symbols.append(symbol)
            active_function = symbol
            brace_depth = line.count("{") - line.count("}")
            continue

        import_match = _JS_IMPORT_RE.match(line)
        if import_match:
            target = import_match.group(1)
            name = target.rsplit("/", 1)[-1] or target
            symbol = SymbolRecord(
                name=name,
                qualname=".".join(part for part in [module_prefix, name] if part),
                kind="import",
                line=idx,
                end_line=idx,
                code=stripped,
            )
            symbol.imports.append((target, idx))
            symbols.append(symbol)

        var_match = _JS_VAR_RE.match(line)
        if var_match and line_depth == 0 and "=>" not in line and "function" not in line:
            name = var_match.group(1)
            kind = "constant" if line.lstrip().startswith("const ") or f"const {name}" in line else "variable"
            symbols.append(
                SymbolRecord(
                    name=name,
                    qualname=".".join(part for part in [module_prefix, name] if part),
                    kind=kind,
                    line=idx,
                    end_line=idx,
                    code=stripped,
                )
            )

        if active_function is not None:
            for call_match in _JS_CALL_RE.finditer(line):
                call = call_match.group(1)
                if call in {"if", "for", "while", "switch", "function"}:
                    continue
                active_function.calls.append((call, idx))
                if call.rsplit(".", 1)[-1][:1].isupper():
                    active_function.instantiates.append((call, idx))
            brace_depth += line.count("{") - line.count("}")
            active_function.end_line = idx
            active_function.code = "\n".join(lines[active_function.line - 1 : idx])
            if brace_depth <= 0 and "{" in line:
                active_function = None
        global_depth += line.count("{") - line.count("}")

    return symbols


def extract_source(source: str, language: str, module_prefix: str = "") -> list[SymbolRecord]:
    if language == "python":
        return extract_python(source, module_prefix=module_prefix)
    if language == "javascript":
        return extract_javascript(source, module_prefix=module_prefix)
    return []


def rebuild_project(conn: Any, project_path: str, project_name: str | None = None) -> dict[str, int | str]:
    root = Path(project_path).resolve()
    if not root.exists():
        raise FileNotFoundError(str(root))
    ensure_schema(conn)
    previous_autocommit = getattr(conn, "autocommit", None)
    if previous_autocommit is not None:
        conn.autocommit = False
    name = project_name or root.name
    source_files = _iter_source_files(root)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pgcg_projects(name, root_path, indexed_at)
                VALUES (%s, %s, now())
                ON CONFLICT (name) DO UPDATE SET root_path = EXCLUDED.root_path, indexed_at = now()
                RETURNING id
                """,
                (name, str(root)),
            )
            project_id = cur.fetchone()[0]
            cur.execute("DELETE FROM pgcg_files WHERE project_id = %s", (project_id,))
            file_symbol_rows: list[tuple[int, int, SymbolRecord]] = []
            contains_rows: list[tuple[int, int, int]] = []
            file_node_by_file_id: dict[int, int] = {}
            file_count = 0
            symbol_count = 0
            for path in source_files:
                rel_path = path.relative_to(root).as_posix()
                language = SOURCE_SUFFIXES[path.suffix.lower()]
                try:
                    content = path.read_text(encoding="utf-8-sig")
                    module_prefix = str(Path(rel_path).with_suffix("")).replace("\\", "/").replace("/", ".")
                    symbols = extract_source(content, language=language, module_prefix=module_prefix)
                except (UnicodeDecodeError, SyntaxError):
                    continue
                stat = path.stat()
                cur.execute(
                    """
                    INSERT INTO pgcg_files(project_id, path, rel_path, language, sha256, mtime, size_bytes, content)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        project_id,
                        str(path),
                        rel_path,
                        language,
                        hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        stat.st_mtime,
                        stat.st_size,
                        content,
                    ),
                )
                file_id = cur.fetchone()[0]
                file_count += 1
                file_symbol = SymbolRecord(
                    name=rel_path,
                    qualname=rel_path,
                    kind="file",
                    line=1,
                    end_line=max(1, len(content.splitlines())),
                    code="",
                )
                cur.execute(
                    """
                    INSERT INTO pgcg_symbols(project_id, file_id, name, qualname, kind, line, end_line, signature, docstring, code)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        project_id,
                        file_id,
                        file_symbol.name,
                        file_symbol.qualname,
                        file_symbol.kind,
                        file_symbol.line,
                        file_symbol.end_line,
                        file_symbol.signature,
                        file_symbol.docstring,
                        file_symbol.code,
                    ),
                )
                file_symbol_id = cur.fetchone()[0]
                file_node_by_file_id[file_id] = file_symbol_id
                file_symbol_rows.append((file_symbol_id, file_id, file_symbol))
                symbol_count += 1
                for symbol in symbols:
                    cur.execute(
                        """
                        INSERT INTO pgcg_symbols(project_id, file_id, name, qualname, kind, line, end_line, signature, docstring, code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            project_id,
                            file_id,
                            symbol.name,
                            symbol.qualname,
                            symbol.kind,
                            symbol.line,
                            symbol.end_line,
                            symbol.signature,
                            symbol.docstring,
                            symbol.code,
                        ),
                    )
                    symbol_id = cur.fetchone()[0]
                    file_symbol_rows.append((symbol_id, file_id, symbol))
                    if symbol.kind != "route":
                        contains_rows.append((file_symbol_id, symbol_id, file_id))
                    symbol_count += 1
            by_qualname: dict[str, int] = {}
            name_counts: dict[str, int] = {}
            first_by_name: dict[str, int] = {}
            symbol_kind_by_id: dict[int, str] = {}
            same_file_counts: dict[tuple[int, str], int] = {}
            first_by_file_name: dict[tuple[int, str], int] = {}
            cur.execute("SELECT id, file_id, name, qualname, kind FROM pgcg_symbols WHERE project_id = %s", (project_id,))
            for symbol_id, symbol_file_id, simple_name, qualname, kind in cur.fetchall():
                by_qualname.setdefault(qualname, symbol_id)
                first_by_name.setdefault(simple_name, symbol_id)
                name_counts[simple_name] = name_counts.get(simple_name, 0) + 1
                symbol_kind_by_id[symbol_id] = kind
                file_key = (symbol_file_id, simple_name)
                first_by_file_name.setdefault(file_key, symbol_id)
                same_file_counts[file_key] = same_file_counts.get(file_key, 0) + 1
            by_name = {name: symbol_id for name, symbol_id in first_by_name.items() if name_counts.get(name) == 1}
            by_file_name = {key: symbol_id for key, symbol_id in first_by_file_name.items() if same_file_counts.get(key) == 1}
            edge_rows: list[tuple[int, int, int | None, int, str, str, int]] = []
            for source_id, file_id, symbol in file_symbol_rows:
                if symbol.kind == "file":
                    continue
                for target_name, line in symbol.calls:
                    short_name = target_name.rsplit(".", 1)[-1]
                    target_id = by_qualname.get(target_name) or by_file_name.get((file_id, short_name)) or by_name.get(short_name)
                    if target_id is not None:
                        edge_rows.append((project_id, source_id, target_id, file_id, "calls", target_name, line))
                if symbol.kind == "import":
                    code = symbol.code.lstrip()
                    if code.startswith("from ") or (code.startswith("import ") and symbol.name.endswith(".js")):
                        edge_rows.append((project_id, file_node_by_file_id[file_id], source_id, file_id, "imports", symbol.name, symbol.line))
                for target_name, line in symbol.extends:
                    short_name = target_name.rsplit(".", 1)[-1]
                    target_id = by_qualname.get(target_name) or by_name.get(short_name)
                    if target_id is not None:
                        edge_rows.append((project_id, source_id, target_id, file_id, "extends", target_name, line))
                for target_name, line in symbol.instantiates:
                    short_name = target_name.rsplit(".", 1)[-1]
                    target_id = by_qualname.get(target_name) or by_file_name.get((file_id, short_name)) or first_by_name.get(short_name)
                    if target_id is not None:
                        edge_rows.append((project_id, source_id, target_id, file_id, "instantiates", target_name, line))
                call_refs = {(name.rsplit(".", 1)[-1], line) for name, line in symbol.calls}
                instantiate_refs = {(name.rsplit(".", 1)[-1], line) for name, line in symbol.instantiates}
                for target_name, line in symbol.references[:25]:
                    if (target_name, line) in call_refs or (target_name, line) in instantiate_refs:
                        continue
                    short_name = target_name.rsplit(".", 1)[-1]
                    target_id = by_qualname.get(target_name) or by_name.get(short_name)
                    if target_id is not None and symbol_kind_by_id.get(target_id) in {"class", "function"}:
                        edge_rows.append((project_id, source_id, target_id, file_id, "references", target_name, line))
            for source_id, target_id, contains_file_id in contains_rows:
                edge_rows.append((project_id, source_id, target_id, contains_file_id, "contains", "", 1))
            if edge_rows:
                from psycopg2.extras import execute_values

                execute_values(
                    cur,
                    """
                    INSERT INTO pgcg_edges(project_id, source_symbol_id, target_symbol_id, file_id, kind, target_name, line)
                    VALUES %s
                    """,
                    edge_rows,
                    page_size=1000,
                )
        conn.commit()
        return {
            "project": name,
            "project_path": str(root),
            "files": file_count,
            "symbols": symbol_count,
            "edges": len(edge_rows),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        if previous_autocommit is not None:
            conn.autocommit = previous_autocommit
