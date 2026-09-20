"""
AST Tools for Structural Code Mapping.

Provides high-performance code signature harvesting across Python, JavaScript,
TypeScript, and JSX/TSX. Strips execution logic, loops, and implementation bodies
while preserving class definitions, methods, functions, Express/HTTP routes,
React component structures, TypeScript interfaces, and docstrings.
Reduces token consumption by 80-90% while retaining structural awareness.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from context.estimator import TokenEstimator

# Attempt optional tree-sitter imports for robust AST parsing
try:
    from tree_sitter import Language, Parser
    import tree_sitter_javascript as tsjs
    import tree_sitter_typescript as tst

    HAS_TREE_SITTER = True
    JS_LANGUAGE = Language(tsjs.language())
    TS_LANGUAGE = Language(tst.language_typescript())
    TSX_LANGUAGE = Language(tst.language_tsx())
except Exception:
    HAS_TREE_SITTER = False
    JS_LANGUAGE = None
    TS_LANGUAGE = None
    TSX_LANGUAGE = None


class ASTTools:
    """
    Handler for AST-based code signature extraction and structural code mapping.
    Strips deep execution bodies to conserve context window while retaining
    exact APIs, route definitions, signatures, and interfaces.
    """

    SUPPORTED_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
    }

    def __init__(self, sandbox_path: Path, is_safe_path_fn: Callable[[str], bool]):
        self.sandbox_path = Path(sandbox_path).resolve()
        self._is_safe_path = is_safe_path_fn

    def extract_signatures(self, file_path: str) -> str:
        """
        Extracts structural code signatures (classes, methods, functions, Express routes,
        interfaces, exports, docstrings) from Python, JavaScript, TypeScript, or JSX files,
        stripping interior execution bodies. Saves 80-90% of tokens while retaining full
        architectural awareness.

        Args:
            file_path: Relative path to the file to inspect (e.g. 'server/index.js', 'src/App.jsx', 'app.py').

        Returns:
            A clean structural outline of the code with execution bodies stripped, along with
            token reduction statistics.
        """
        if not file_path or not str(file_path).strip():
            return "Error: 'file_path' is required to extract signatures."

        clean_file_path = str(file_path).strip()
        if not self._is_safe_path(clean_file_path):
            return f"Error: Access denied to path outside sandbox: {clean_file_path}"

        clean_path = os.path.normpath(clean_file_path).lstrip("/").replace("\\", "/")
        target = self.sandbox_path / clean_path

        if not target.exists():
            return f"Error: Target file does not exist: {clean_file_path}"
        if target.is_dir():
            return (
                f"Error: Target path is a directory, not a file: {file_path}. "
                f"Use locate_files_by_pattern to inspect directory topology."
            )

        suffix = target.suffix.lower()
        lang = self.SUPPORTED_EXTENSIONS.get(suffix)

        if not lang:
            supported_list = ", ".join(sorted(self.SUPPORTED_EXTENSIONS.keys()))
            return (
                f"Notice: extract_signatures currently supports {supported_list}. "
                f"For '{clean_path}', please use read_file(file_path='{clean_path}') instead."
            )

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file '{clean_path}': {str(e)}"

        if not content.strip():
            return f"[AST Signature Map: {clean_path} | Empty file (0 lines)]\n"

        orig_lines = len(content.splitlines())
        orig_tokens = TokenEstimator.estimate_text(content)

        try:
            if lang == "python":
                signatures = self._extract_python_signatures(content, clean_path)
            elif lang in ("javascript", "jsx", "typescript", "tsx"):
                is_ts = lang in ("typescript", "tsx")
                is_jsx = lang in ("jsx", "tsx") or suffix in (".jsx", ".tsx")
                signatures = self._extract_js_signatures(content, clean_path, is_ts=is_ts, is_jsx=is_jsx)
            else:
                signatures = content
        except Exception as e:
            # Fallback to pure regex extractor if AST parsing encountered unexpected failure
            signatures = self._fallback_regex_extractor(content, lang)

        sig_lines = len(signatures.splitlines())
        sig_tokens = TokenEstimator.estimate_text(signatures)
        reduction_pct = max(0, 100 - (sig_tokens * 100 // orig_tokens)) if orig_tokens > 0 else 0

        header = (
            f"[AST Signature Map: {clean_path} | {orig_lines} -> {sig_lines} lines | "
            f"~{orig_tokens} -> ~{sig_tokens} tokens ({reduction_pct}% token reduction)]\n\n"
        )
        return header + signatures

    # ─────────────────────────────────────────────────────────────
    # Python AST Extractor
    # ─────────────────────────────────────────────────────────────

    def _extract_python_signatures(self, content: str, rel_path: str) -> str:
        """Extracts Python class and function signatures using the standard library ast module."""
        tree = ast.parse(content, filename=rel_path)

        new_body: List[ast.stmt] = []

        # Retain module docstring if present
        mod_doc = ast.get_docstring(tree)
        if mod_doc:
            new_body.append(ast.Expr(value=ast.Constant(value=mod_doc)))

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                new_body.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_body.append(self._strip_python_function(node))
            elif isinstance(node, ast.ClassDef):
                new_body.append(self._strip_python_class(node))
            elif isinstance(node, ast.AnnAssign):
                # Global typed declarations (e.g. RAM_HEADER: str = "...")
                new_body.append(node)
            elif isinstance(node, ast.Assign):
                # Retain simple global constant assignments (e.g. ALL_CAPS = ...)
                if any(isinstance(target, ast.Name) and target.id.isupper() for target in node.targets):
                    new_body.append(node)

        tree.body = new_body
        return ast.unparse(tree)

    def _strip_python_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.FunctionDef | ast.AsyncFunctionDef:
        """Replaces a Python function body with its docstring (if present) and ellipsis (...)."""
        doc = ast.get_docstring(node)
        new_body: List[ast.stmt] = []
        if doc:
            new_body.append(ast.Expr(value=ast.Constant(value=doc)))
        new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))
        node.body = new_body
        return node

    def _strip_python_class(self, node: ast.ClassDef) -> ast.ClassDef:
        """Replaces interior method bodies in a class while retaining docstrings and class attributes."""
        class_doc = ast.get_docstring(node)
        new_class_body: List[ast.stmt] = []
        if class_doc:
            new_class_body.append(ast.Expr(value=ast.Constant(value=class_doc)))

        for sub in node.body:
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                new_class_body.append(self._strip_python_function(sub))
            elif isinstance(sub, ast.AnnAssign):
                new_class_body.append(sub)
            elif isinstance(sub, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id.isupper() for target in sub.targets):
                    new_class_body.append(sub)

        if not new_class_body:
            new_class_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))

        node.body = new_class_body
        return node

    # ─────────────────────────────────────────────────────────────
    # JavaScript / TypeScript / JSX Tree-Sitter Extractor
    # ─────────────────────────────────────────────────────────────

    def _extract_js_signatures(self, content: str, rel_path: str, is_ts: bool = False, is_jsx: bool = False) -> str:
        """Extracts JS/TS/JSX signatures using tree-sitter or pure Python fallback."""
        if not HAS_TREE_SITTER:
            return self._fallback_regex_extractor(content, "javascript")

        # Pick language parser
        if is_jsx or rel_path.endswith((".jsx", ".tsx")):
            parser = Parser(TSX_LANGUAGE if is_ts else JS_LANGUAGE)
        elif is_ts:
            parser = Parser(TS_LANGUAGE)
        else:
            parser = Parser(JS_LANGUAGE)

        source_bytes = content.encode("utf-8")
        tree = parser.parse(source_bytes)

        edits: List[Tuple[int, int, bytes]] = []

        def is_react_component(node: Any) -> bool:
            """Detects if a function is likely a React component (capitalized name)."""
            name_node = node.child_by_field_name("name")
            if name_node and name_node.text:
                name = name_node.text.decode("utf-8", errors="ignore")
                if name and name[0].isupper():
                    return True
            if node.parent and node.parent.type == "variable_declarator":
                var_name_node = node.parent.child_by_field_name("name")
                if var_name_node and var_name_node.text:
                    name = var_name_node.text.decode("utf-8", errors="ignore")
                    if name and name[0].isupper():
                        return True
            return False

        def walk(n: Any, inside_component: bool = False) -> None:
            if n.type in ("function_declaration", "function_expression", "arrow_function", "method_definition"):
                is_comp = is_react_component(n)
                body_node = n.child_by_field_name("body")

                if is_comp and body_node and body_node.type == "statement_block":
                    # React components: preserve inner hooks and handler signatures, collapse return JSX block
                    for stmt in body_node.children:
                        if stmt.type == "return_statement":
                            edits.append((stmt.start_byte, stmt.end_byte, b"return (/* ... JSX ... */);"))
                        else:
                            walk(stmt, inside_component=True)
                    return
                elif body_node and body_node.type == "statement_block":
                    edits.append((body_node.start_byte, body_node.end_byte, b"{ /* ... */ }"))
                    return

            elif n.type in ("array", "object"):
                # Collapse large data literals (>3 lines) assigned to top-level variables
                lines_span = n.end_point[0] - n.start_point[0]
                if lines_span > 3 and n.parent and n.parent.type in ("variable_declarator", "assignment_expression"):
                    repl = b"[ /* ... */ ]" if n.type == "array" else b"{ /* ... */ }"
                    edits.append((n.start_byte, n.end_byte, repl))
                    return

            for child in n.children:
                walk(child, inside_component=inside_component)

        walk(tree.root_node)

        # Apply edits from end of file to beginning to preserve byte offsets
        edits.sort(key=lambda x: x[0], reverse=True)
        res = bytearray(source_bytes)
        for start, end, repl in edits:
            res[start:end] = repl

        return res.decode("utf-8", errors="replace")

    # ─────────────────────────────────────────────────────────────
    # Pure Python Resilient Fallback Extractor
    # ─────────────────────────────────────────────────────────────

    def _fallback_regex_extractor(self, content: str, lang: str) -> str:
        """
        Pure-Python fallback signature extractor for JS/TS/JSX when
        tree-sitter is unavailable or source has syntax anomalies.
        """
        lines = content.splitlines()
        output: List[str] = []
        i = 0
        n = len(lines)

        def skip_braces(start_idx: int) -> int:
            """Advances line index until all opened braces are closed."""
            idx = start_idx
            cur = lines[idx]
            count = cur.count("{") - cur.count("}")
            while idx + 1 < n and count > 0:
                idx += 1
                count += lines[idx].count("{") - lines[idx].count("}")
            return idx

        def is_component_decl(line_str: str) -> bool:
            """Checks if line declares a React component (starts with an uppercase identifier)."""
            if re.search(r"\bfunction\s+([A-Z][a-zA-Z0-9_$]*)", line_str):
                return True
            if re.search(r"\b(?:const|let|var)\s+([A-Z][a-zA-Z0-9_$]*)\s*=", line_str):
                return True
            return False

        while i < n:
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                output.append("")
                i += 1
                continue

            # 1. Keep comments
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                output.append(line)
                i += 1
                continue

            # 2. Keep imports, requires, type aliases, interfaces, enums
            if (
                stripped.startswith("import ")
                or "require(" in stripped
                or stripped.startswith("export type ")
                or stripped.startswith("export interface ")
                or stripped.startswith("interface ")
                or stripped.startswith("type ")
                or stripped.startswith("export enum ")
                or stripped.startswith("enum ")
            ):
                output.append(line)
                i += 1
                continue

            # 3. Express / HTTP routes & server listeners (e.g. app.get, router.post, app.listen)
            route_pattern = r"^(\s*(?:app|router)\.(?:get|post|put|delete|patch|use|all|options|head|listen)\s*\()"
            if re.match(route_pattern, line):
                is_multiline = (
                    "{" not in line
                    and not stripped.endswith(";")
                    and (line.count("(") > line.count(")") or stripped.endswith(","))
                    and (i + 1 < n)
                    and any("{" in lines[j] for j in range(i + 1, min(n, i + 6)))
                )
                if is_multiline:
                    accum = [line]
                    while i + 1 < n and "{" not in lines[i]:
                        i += 1
                        accum.append(lines[i])
                    idx = lines[i].rfind("{")
                    accum[-1] = lines[i][:idx].rstrip()
                    header = "\n".join(accum)
                    i = skip_braces(i)
                    if i + 1 < n and lines[i + 1].strip().startswith(")"):
                        i += 1
                    output.append(f"{header} {{ /* ... */ }});")
                    i += 1
                    continue
                elif "{" in line:
                    idx = line.rfind("{")
                    header = line[:idx].rstrip()
                    i = skip_braces(i)
                    if i + 1 < n and lines[i + 1].strip().startswith(")"):
                        i += 1
                    output.append(f"{header} {{ /* ... */ }});")
                    i += 1
                    continue
                else:
                    output.append(line)
                    i += 1
                    continue

            # 4. React Components (functions/arrows with uppercase names)
            if is_component_decl(line):
                if "{" in line:
                    output.append(line)
                    component_depth = line.count("{") - line.count("}")
                    i += 1
                    while i < n and component_depth > 0:
                        cline = lines[i]
                        cstripped = cline.strip()
                        component_depth += cline.count("{") - cline.count("}")

                        if not cstripped:
                            output.append("")
                            i += 1
                            continue

                        if cstripped.startswith("//") or cstripped.startswith("/*") or cstripped.startswith("*"):
                            output.append(cline)
                            i += 1
                            continue

                        # Hooks: useState, useRef, useMemo, useContext, etc.
                        if re.match(r"^\s*(?:const|let|var)\s+.*?\buse[A-Z]", cline) and ("{" not in cline or cline.endswith(";")):
                            output.append(cline)
                            i += 1
                            continue

                        # useEffect / custom hooks with callback blocks
                        if re.match(r"^\s*use[A-Z]", cline) and "{" in cline:
                            hook_match = re.match(r"^(\s*use[A-Za-z0-9_$]+\s*\(\s*(?:async\s*)?\([^)]*\)\s*=>)", cline)
                            if hook_match:
                                hook_header = hook_match.group(1).rstrip()
                                i = skip_braces(i)
                                end_line = lines[i].strip()
                                dep = ""
                                if "," in end_line:
                                    dep = ", " + end_line.split(",", 1)[1].rstrip(";").rstrip(")").strip()
                                output.append(f"{hook_header} {{ /* ... */ }}{dep});")
                                i += 1
                                continue
                            else:
                                i = skip_braces(i)
                                output.append("    /* ... hook ... */")
                                i += 1
                                continue

                        # Inner handlers / arrow functions: const handleAdd = async (...) => { ... }
                        inner_arrow = re.match(r"^(\s*(?:const|let|var)\s+[a-zA-Z0-9_$]+\s*(?::\s*[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[a-zA-Z0-9_$]+)\s*(?::\s*[^=]+)?=>\s*)\{?", cline)
                        if inner_arrow and ("{" in cline or (i + 1 < n and "{" in lines[i + 1])):
                            arrow_header = inner_arrow.group(1).rstrip()
                            i = skip_braces(i)
                            output.append(f"{arrow_header} {{ /* ... */ }};")
                            i += 1
                            continue

                        # Inner function declarations: function handleDelete(...) { ... }
                        inner_fn = re.match(r"^(\s*(?:async\s+)?function\s+[a-zA-Z0-9_$]+\s*\([^)]*\)\s*(?::\s*[^{]+)?)\s*\{?", cline)
                        if inner_fn and ("{" in cline or (i + 1 < n and "{" in lines[i + 1])):
                            fn_header = inner_fn.group(1).rstrip()
                            i = skip_braces(i)
                            output.append(f"{fn_header} {{ /* ... */ }}")
                            i += 1
                            continue

                        # JSX return statement: return ( ... ); or return <...>;
                        if cstripped.startswith("return (") or cstripped.startswith("return <") or cstripped == "return":
                            indent = cline[:len(cline) - len(cstripped)]
                            paren_count = cline.count("(") - cline.count(")")
                            brace_inner = cline.count("{") - cline.count("}")
                            while i + 1 < n and (paren_count > 0 or (brace_inner > 0 and component_depth > 1) or not (cstripped.endswith(";") or cstripped.endswith(")"))):
                                i += 1
                                cline = lines[i]
                                cstripped = cline.strip()
                                paren_count += cline.count("(") - cline.count(")")
                                component_depth += cline.count("{") - cline.count("}")
                                if component_depth <= 1 and (cstripped.endswith(");") or cstripped.endswith(";")):
                                    break
                            output.append(f"{indent}return (/* ... JSX ... */);")
                            i += 1
                            continue

                        # Closing brace of component
                        if component_depth == 0 or cstripped == "}":
                            output.append(cline)
                            i += 1
                            break

                        output.append(cline)
                        i += 1
                    continue
                else:
                    output.append(line)
                    i += 1
                    continue

            # 5. Class declarations & class bodies
            class_match = re.match(r"^(\s*(?:export\s+)?(?:default\s+)?class\s+[a-zA-Z0-9_$]+(?:\s+extends\s+[a-zA-Z0-9_$.]+)?(?:\s+implements\s+[^{]+)?\s*)\{?", line)
            if class_match and "{" in line:
                output.append(line)
                class_depth = line.count("{") - line.count("}")
                i += 1
                while i < n and class_depth > 0:
                    cline = lines[i]
                    cstripped = cline.strip()
                    class_depth += cline.count("{") - cline.count("}")

                    if not cstripped:
                        output.append("")
                        i += 1
                        continue

                    if cstripped.startswith("//") or cstripped.startswith("/*") or cstripped.startswith("*"):
                        output.append(cline)
                        i += 1
                        continue

                    # Class properties (e.g. private tokenSecret: string; or count = 0;)
                    if ("{" not in cline and cstripped.endswith(";")) or (":" in cstripped and "{" not in cline):
                        output.append(cline)
                        i += 1
                        continue

                    # Class constructors and methods:
                    if "{" in cline:
                        idx = cline.rfind("{")
                        method_header = cline[:idx].rstrip()
                        i = skip_braces(i)
                        output.append(f"{method_header} {{ /* ... */ }}")
                        i += 1
                        continue

                    if class_depth == 0 or cstripped == "}":
                        output.append(cline)
                        i += 1
                        break

                    output.append(cline)
                    i += 1
                continue

            # 6. Standard top-level function declarations
            fn_match = re.match(r"^(\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*[a-zA-Z0-9_$]*\s*\([^)]*\)\s*(?::\s*[^{]+)?)\s*\{?", line)
            if fn_match:
                header = fn_match.group(1).rstrip()
                if line.count("{") > 0 or "{" in line:
                    i = skip_braces(i)
                    output.append(f"{header} {{ /* ... */ }}")
                else:
                    output.append(line)
                i += 1
                continue

            # 7. Standard top-level arrow functions
            arrow_match = re.match(r"^(\s*(?:export\s+)?(?:const|let|var)\s+[a-zA-Z0-9_$]+\s*(?::\s*[^=]+)?=\s*(?:async\s*)?(?:\([^)]*\)|[a-zA-Z0-9_$]+)\s*(?::\s*[^=]+)?=>\s*)\{?", line)
            if arrow_match:
                header = arrow_match.group(1).rstrip()
                if line.count("{") > 0 or "{" in line:
                    i = skip_braces(i)
                    output.append(f"{header}{{ /* ... */ }};")
                else:
                    output.append(line)
                i += 1
                continue

            # 8. Large data arrays or objects
            if stripped.startswith("let ") or stripped.startswith("const ") or stripped.startswith("var "):
                if "[" in stripped or "{" in stripped:
                    var_name = stripped.split("=")[0].strip()
                    bracket_count = line.count("[") + line.count("{") - line.count("]") - line.count("}")
                    if bracket_count > 0:
                        while i + 1 < n and bracket_count > 0:
                            i += 1
                            bracket_count += lines[i].count("[") + lines[i].count("{") - lines[i].count("]") - lines[i].count("}")
                        output.append(f"{var_name} = [ /* ... */ ];")
                        i += 1
                        continue

            output.append(line)
            i += 1

        return "\n".join(output)

    # ─────────────────────────────────────────────────────────────
    # Repository Dependency & Import/Export Graph Mapping (CP-105.1)
    # ─────────────────────────────────────────────────────────────

    IGNORE_DIRS = {
        ".git",
        "node_modules",
        "dist",
        "build",
        "venv",
        ".next",
        "__pycache__",
        ".lowkey",
        ".cache",
        "coverage",
    }

    CANDIDATE_EXTENSIONS = [
        "",
        ".jsx",
        ".js",
        ".tsx",
        ".ts",
        ".mjs",
        ".cjs",
        ".css",
        ".json",
        ".py",
    ]

    INDEX_EXTENSIONS = [
        "index.jsx",
        "index.js",
        "index.tsx",
        "index.ts",
        "__init__.py",
    ]

    def map_dependencies(self, target_file: Optional[str] = None) -> str:
        """
        Maps repository import/export relationships across the workspace.
        When target_file is provided, performs an impact analysis detailing what the file imports,
        what it exports, and all downstream files that depend on it.
        When target_file is omitted, returns a complete workspace dependency topology map.

        Args:
            target_file: Optional relative path to a specific file to audit for dependencies and impact.

        Returns:
            A structured visual dependency report with impact analysis and external packages.
        """
        # 1. Targeted file validation if provided
        clean_target = None
        if target_file and target_file.strip():
            target_str = target_file.strip()
            if not self._is_safe_path(target_str):
                return f"Error: Access denied to path outside sandbox: {target_str}"

            clean_target = os.path.normpath(target_str).lstrip("/").replace("\\", "/")
            target_path = self.sandbox_path / clean_target

            if not target_path.exists():
                return f"Error: Target file does not exist: {target_str}"
            if target_path.is_dir():
                return f"Error: Target path is a directory: {target_str}. Please provide a file path or omit target_file to map the whole project."

        # 2. Discover all project source files
        source_files = self._discover_source_files()
        if not source_files:
            return "Notice: No source code files (.js, .jsx, .ts, .tsx, .py) discovered in the workspace."

        # 3. Build bidirectional dependency graph
        graph = self._build_dependency_graph(source_files)

        # 4. Return targeted report or whole-workspace map
        if clean_target:
            return self._format_target_file_report(clean_target, graph)
        else:
            return self._format_workspace_graph_report(graph)

    def _discover_source_files(self) -> List[Path]:
        """Discovers all source code files in the sandbox, filtering out ignored directories."""
        discovered: List[Path] = []
        for root, dirs, files in os.walk(self.sandbox_path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS and not d.startswith(".")]

            for file in files:
                suffix = Path(file).suffix.lower()
                if suffix in self.SUPPORTED_EXTENSIONS:
                    full_p = Path(root) / file
                    discovered.append(full_p)
        return sorted(discovered)

    def _resolve_relative_import(self, import_spec: str, source_file: Path) -> Optional[str]:
        """Resolves an import specifier string to a normalized workspace-relative file path."""
        import_spec = import_spec.strip().replace("\\", "/")
        source_dir = source_file.parent

        candidate_bases: List[Path] = []

        if import_spec.startswith("./") or import_spec.startswith("../") or import_spec == "." or import_spec == "..":
            candidate_bases.append((source_dir / import_spec).resolve())
        elif import_spec.startswith("@/") or import_spec.startswith("~/"):
            # Vite / Webpack path alias for src/
            candidate_bases.append((self.sandbox_path / "src" / import_spec[2:]).resolve())
        elif import_spec.startswith("src/"):
            candidate_bases.append((self.sandbox_path / import_spec).resolve())
        else:
            # Check relative to baseUrl "src" (e.g. components/Header -> src/components/Header)
            candidate_bases.append((self.sandbox_path / "src" / import_spec).resolve())
            # Check relative to baseUrl "." (e.g. components/Header -> components/Header)
            candidate_bases.append((self.sandbox_path / import_spec).resolve())
            # Check alias like @components/Button -> src/components/Button
            if import_spec.startswith("@") and not import_spec.startswith("@/"):
                stripped = import_spec.lstrip("@")
                candidate_bases.append((self.sandbox_path / "src" / stripped).resolve())

        for target_base in candidate_bases:
            try:
                if not target_base.is_relative_to(self.sandbox_path):
                    continue
            except ValueError:
                continue

            # Check if candidate matches an existing file
            if target_base.is_file():
                try:
                    return str(target_base.relative_to(self.sandbox_path)).replace("\\", "/")
                except ValueError:
                    continue

            # Try appending extensions
            for ext in self.CANDIDATE_EXTENSIONS:
                if not ext:
                    continue
                cand = target_base.with_name(target_base.name + ext)
                if cand.is_file():
                    try:
                        return str(cand.relative_to(self.sandbox_path)).replace("\\", "/")
                    except ValueError:
                        continue

            # Try index files inside directory
            if target_base.is_dir():
                for idx in self.INDEX_EXTENSIONS:
                    cand = target_base / idx
                    if cand.is_file():
                        try:
                            return str(cand.relative_to(self.sandbox_path)).replace("\\", "/")
                        except ValueError:
                            continue

        return None

    def _get_python_search_roots(self, file_path: Path) -> List[Path]:
        """Returns prioritized candidate search roots for resolving Python imports."""
        roots: List[Path] = [file_path.parent]
        p = file_path.parent
        while p != self.sandbox_path and p.is_relative_to(self.sandbox_path):
            p = p.parent
            if p not in roots:
                roots.append(p)
        if self.sandbox_path not in roots:
            roots.append(self.sandbox_path)
        for sub in ("src", "backend", "app", "server"):
            cand = self.sandbox_path / sub
            if cand.is_dir() and cand not in roots:
                roots.append(cand)
        return roots

    def _find_python_module(self, file_path: Path, mod_name: str) -> Optional[str]:
        """Resolves a Python module or package to a workspace-relative file path."""
        mod_path = mod_name.replace(".", "/")
        for root in self._get_python_search_roots(file_path):
            cand_py = root / f"{mod_path}.py"
            if cand_py.is_file() and cand_py.is_relative_to(self.sandbox_path):
                return str(cand_py.relative_to(self.sandbox_path)).replace("\\", "/")
            cand_pkg = root / mod_path / "__init__.py"
            if cand_pkg.is_file() and cand_pkg.is_relative_to(self.sandbox_path):
                return str(cand_pkg.relative_to(self.sandbox_path)).replace("\\", "/")
        return None

    def _resolve_python_import_from(
        self, file_path: Path, level: int, mod_name: Optional[str], imported_names: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Resolves from-imports in Python files (e.g. from . import X or from models import user)."""
        local_imports: List[str] = []
        external_pkgs: List[str] = []

        if level > 0:
            rel_dir = file_path.parent
            for _ in range(level - 1):
                if rel_dir.parent.is_relative_to(self.sandbox_path):
                    rel_dir = rel_dir.parent

            if mod_name:
                mod_path = mod_name.replace(".", "/")
                cand_py = rel_dir / f"{mod_path}.py"
                cand_pkg = rel_dir / mod_path / "__init__.py"
                if cand_py.is_file():
                    local_imports.append(str(cand_py.relative_to(self.sandbox_path)).replace("\\", "/"))
                elif cand_pkg.is_file():
                    sub_found = False
                    for name in imported_names:
                        cand_sub = rel_dir / mod_path / f"{name}.py"
                        if cand_sub.is_file():
                            local_imports.append(str(cand_sub.relative_to(self.sandbox_path)).replace("\\", "/"))
                            sub_found = True
                    if not sub_found:
                        local_imports.append(str(cand_pkg.relative_to(self.sandbox_path)).replace("\\", "/"))
                else:
                    for name in imported_names:
                        cand_sub = rel_dir / mod_path / f"{name}.py"
                        if cand_sub.is_file():
                            local_imports.append(str(cand_sub.relative_to(self.sandbox_path)).replace("\\", "/"))
            else:
                # e.g. from . import utils, helpers
                for name in imported_names:
                    cand_py = rel_dir / f"{name}.py"
                    cand_pkg = rel_dir / name / "__init__.py"
                    if cand_py.is_file():
                        local_imports.append(str(cand_py.relative_to(self.sandbox_path)).replace("\\", "/"))
                    elif cand_pkg.is_file():
                        local_imports.append(str(cand_pkg.relative_to(self.sandbox_path)).replace("\\", "/"))
                if not local_imports:
                    cand_init = rel_dir / "__init__.py"
                    if cand_init.is_file():
                        local_imports.append(str(cand_init.relative_to(self.sandbox_path)).replace("\\", "/"))
        else:
            if not mod_name:
                return local_imports, external_pkgs

            mod_path = mod_name.replace(".", "/")
            found_base = False
            for root in self._get_python_search_roots(file_path):
                cand_py = root / f"{mod_path}.py"
                cand_pkg = root / mod_path / "__init__.py"

                if cand_py.is_file() and cand_py.is_relative_to(self.sandbox_path):
                    local_imports.append(str(cand_py.relative_to(self.sandbox_path)).replace("\\", "/"))
                    found_base = True
                    break
                elif cand_pkg.is_file() and cand_pkg.is_relative_to(self.sandbox_path):
                    sub_found = False
                    for name in imported_names:
                        cand_sub = root / mod_path / f"{name}.py"
                        if cand_sub.is_file() and cand_sub.is_relative_to(self.sandbox_path):
                            local_imports.append(str(cand_sub.relative_to(self.sandbox_path)).replace("\\", "/"))
                            sub_found = True
                    if not sub_found:
                        local_imports.append(str(cand_pkg.relative_to(self.sandbox_path)).replace("\\", "/"))
                    found_base = True
                    break
                else:
                    # e.g. from models import user where models/user.py exists
                    for name in imported_names:
                        cand_sub = root / mod_path / f"{name}.py"
                        if cand_sub.is_file() and cand_sub.is_relative_to(self.sandbox_path):
                            local_imports.append(str(cand_sub.relative_to(self.sandbox_path)).replace("\\", "/"))
                            found_base = True
                    if found_base:
                        break

            if not found_base:
                external_pkgs.append(mod_name.split(".")[0])

        return sorted(list(set(local_imports))), sorted(list(set(external_pkgs)))

    def _extract_python_exports(self, tree: ast.AST) -> List[str]:
        """Extracts exported symbol names from Python AST, prioritizing __all__ when present."""
        # 1. Check for explicit __all__
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                            return sorted(list(set(
                                elt.value for elt in node.value.elts
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                            )))
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "__all__":
                    if node.value and isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        return sorted(list(set(
                            elt.value for elt in node.value.elts
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        )))

        # 2. Extract public top-level functions, classes, and variable/instance assignments
        exports: List[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    exports.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    exports.append(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and not t.id.startswith("_"):
                        exports.append(t.id)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and not node.target.id.startswith("_"):
                    exports.append(node.target.id)

        return sorted(list(set(exports)))

    def _extract_js_exports(self, content: str) -> List[str]:
        """Extracts exported symbol names from JavaScript / TypeScript source."""
        exports: List[str] = []

        # 1. Default export
        def_m = re.search(
            r"export\s+default\s+(?:(?:async\s+)?function\*?|class)?\s*([a-zA-Z0-9_$]+)?",
            content,
        )
        if def_m:
            name = def_m.group(1) or "default"
            exports.append(f"default ({name})")

        # 2. Named declaration exports: const, let, var, function, async function, class, interface, type, enum
        for m in re.finditer(
            r"export\s+(?:const|let|var|(?:async\s+)?function\*?|class|interface|type|enum)\s+([a-zA-Z0-9_$]+)",
            content,
        ):
            exports.append(m.group(1))

        # Additional comma-separated declarations (e.g. export const A = 1, B = 2;)
        for m in re.finditer(
            r"export\s+(?:const|let|var)\s+[^;=]+=[^;]+(?:,\s*([a-zA-Z0-9_$]+)\s*=[^;]+)+;",
            content,
        ):
            for extra in re.finditer(r",\s*([a-zA-Z0-9_$]+)\s*=", m.group(0)):
                exports.append(extra.group(1))

        # 3. Export clauses: export { a, b as c }
        for m in re.finditer(r"export\s*\{([^}]+)\}", content):
            for item in m.group(1).split(","):
                parts = item.strip().split()
                if parts:
                    exports.append(parts[-1])

        # 4. export * as Name
        for m in re.finditer(r"export\s+\*\s+as\s+([a-zA-Z0-9_$]+)", content):
            exports.append(m.group(1))

        # 5. CommonJS exports: exports.name = ... or module.exports.name = ...
        for m in re.finditer(r"(?:module\.)?exports\.([a-zA-Z0-9_$]+)\s*=", content):
            exports.append(m.group(1))

        # 6. CommonJS object export: module.exports = { a, b: c }
        for m in re.finditer(r"module\.exports\s*=\s*\{([^}]+)\}", content):
            for item in m.group(1).split(","):
                key = item.split(":")[0].strip()
                if key and re.match(r"^[a-zA-Z0-9_$]+$", key):
                    exports.append(key)

        # 7. Fallback: bare module.exports
        if not exports and "module.exports" in content:
            exports.append("module.exports")

        return sorted(list(set(exports)))

    def _extract_imports_and_exports(self, file_path: Path) -> Tuple[List[str], List[str], List[str]]:
        """
        Extracts (local_imports, external_packages, exports) from a source file.
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return [], [], []

        suffix = file_path.suffix.lower()
        local_imports: List[str] = []
        external_pkgs: List[str] = []
        exports: List[str] = []

        if suffix == ".py":
            try:
                tree = ast.parse(content, filename=str(file_path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            resolved = self._find_python_module(file_path, alias.name)
                            if resolved:
                                local_imports.append(resolved)
                            else:
                                external_pkgs.append(alias.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        level = node.level or 0
                        mod_name = node.module
                        imported_names = [alias.name for alias in node.names]
                        locs, exts = self._resolve_python_import_from(
                            file_path, level, mod_name, imported_names
                        )
                        local_imports.extend(locs)
                        external_pkgs.extend(exts)

                exports = self._extract_python_exports(tree)
            except Exception:
                pass

        elif suffix in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
            import_specs: List[str] = []

            # 1. Match import/export ... from '...'
            for m in re.finditer(
                r"\b(?:import|export)\s+[\s\S]*?\s+from\s*[\x27\x22]([^\x27\x22]+)[\x27\x22]",
                content,
            ):
                import_specs.append(m.group(1).strip())

            # 2. Match bare import '...' (side-effect imports)
            for m in re.finditer(
                r"\bimport\s*[\x27\x22]([^\x27\x22]+)[\x27\x22]",
                content,
            ):
                import_specs.append(m.group(1).strip())

            # 3. Match require('...')
            for m in re.finditer(
                r"\brequire\s*\(\s*[\x27\x22]([^\x27\x22]+)[\x27\x22]\s*\)",
                content,
            ):
                import_specs.append(m.group(1).strip())

            # 4. Match dynamic import('...')
            for m in re.finditer(
                r"\bimport\s*\(\s*[\x27\x22]([^\x27\x22]+)[\x27\x22]\s*\)",
                content,
            ):
                import_specs.append(m.group(1).strip())

            for spec in import_specs:
                if not spec:
                    continue
                resolved = self._resolve_relative_import(spec, file_path)
                if resolved:
                    local_imports.append(resolved)
                elif not (spec.startswith(".") or spec.startswith("/")):
                    # External package
                    if spec.startswith("@") and "/" in spec:
                        pkg_parts = spec.split("/")
                        pkg_name = f"{pkg_parts[0]}/{pkg_parts[1]}"
                    else:
                        pkg_name = spec.split("/")[0]
                    external_pkgs.append(pkg_name)

            exports = self._extract_js_exports(content)

        return sorted(list(set(local_imports))), sorted(list(set(external_pkgs))), sorted(list(set(exports)))

    def _build_dependency_graph(self, source_files: List[Path]) -> Dict[str, Any]:
        """Builds a complete, bidirectional graph of workspace modules."""
        graph: Dict[str, Any] = {
            "files": [],
            "imports": {},           # file -> list of imported local files
            "external_packages": {}, # file -> list of external npm/python packages
            "exports": {},           # file -> list of exported symbols
            "dependents": {},        # file -> list of files that import it
        }

        for file in source_files:
            try:
                rel_path = str(file.relative_to(self.sandbox_path)).replace("\\", "/")
            except ValueError:
                continue

            graph["files"].append(rel_path)
            graph["dependents"].setdefault(rel_path, [])

            loc_imports, ext_pkgs, exps = self._extract_imports_and_exports(file)
            graph["imports"][rel_path] = loc_imports
            graph["external_packages"][rel_path] = ext_pkgs
            graph["exports"][rel_path] = exps

        # Populate inverse dependents mapping
        for src, targets in graph["imports"].items():
            for tgt in targets:
                graph["dependents"].setdefault(tgt, [])
                if src not in graph["dependents"][tgt]:
                    graph["dependents"][tgt].append(src)

        # Sort all lists
        for k in graph["dependents"]:
            graph["dependents"][k].sort()

        return graph

    def _format_target_file_report(self, target_rel: str, graph: Dict[str, Any]) -> str:
        """Formats an impact analysis report for a single target file."""
        exports = graph["exports"].get(target_rel, [])
        local_deps = graph["imports"].get(target_rel, [])
        ext_deps = graph["external_packages"].get(target_rel, [])
        dependents = graph["dependents"].get(target_rel, [])

        is_source_ext = Path(target_rel).suffix.lower() in self.SUPPORTED_EXTENSIONS

        lines = [
            "=============================================================================",
            f"[DEPENDENCY IMPACT ANALYSIS: {target_rel}]",
            "=============================================================================",
            "",
        ]

        if not is_source_ext:
            lines.extend([
                f"ℹ️ NOTICE: '{target_rel}' is not an AST-parseable source file. Exports and dependencies are not available, but downstream project modules importing it are reported below.",
                "",
            ])

        lines.extend([
            f"📦 EXPORTS ({len(exports)} symbol{'s' if len(exports) != 1 else ''}):",
        ])
        if exports:
            for exp in exports:
                lines.append(f"  • {exp}")
        else:
            lines.append("  • (No public exports detected)")

        lines.extend([
            "",
            f"📥 DEPENDENCIES (Imports declared by {target_rel}):",
        ])
        if local_deps:
            lines.append(f"  • Local Project Modules ({len(local_deps)}):")
            for dep in local_deps:
                lines.append(f"    ├── {dep}")
        else:
            lines.append("  • Local Project Modules: (None)")

        if ext_deps:
            lines.append(f"  • External Packages ({len(ext_deps)}):")
            for pkg in ext_deps:
                lines.append(f"    - {pkg}")
        else:
            lines.append("  • External Packages: (None)")

        lines.extend([
            "",
            f"📤 DOWNSTREAM DEPENDENTS ({len(dependents)} file{'s' if len(dependents) != 1 else ''} import this module):",
        ])
        if dependents:
            lines.append(f"  [!] Modifying '{target_rel}' directly impacts:")
            for dep in dependents:
                lines.append(f"    └── {dep}")
        else:
            lines.append("  ✓ (No other project modules import this file; safe for standalone modification)")

        lines.append("=============================================================================")
        return "\n".join(lines)

    def _detect_circular_dependencies(self, imports_map: Dict[str, List[str]]) -> List[str]:
        """Detects circular dependencies of any cycle length (2, 3, or more)."""
        cycles: List[str] = []
        seen_cycle_keys = set()

        def dfs(start_node: str, current_node: str, path: List[str], visited: set[str]):
            for neighbor in imports_map.get(current_node, []):
                if neighbor == start_node and len(path) > 1:
                    # Canonical representation (rotate to smallest element)
                    min_idx = path.index(min(path))
                    canonical = tuple(path[min_idx:] + path[:min_idx])
                    if canonical not in seen_cycle_keys:
                        seen_cycle_keys.add(canonical)
                        if len(canonical) == 2:
                            pair = sorted([canonical[0], canonical[1]])
                            cycles.append(f"{pair[0]} <---> {pair[1]}")
                        else:
                            cycles.append(" -> ".join(canonical) + f" -> {canonical[0]}")
                elif neighbor not in visited and len(path) < 15:
                    dfs(start_node, neighbor, path + [neighbor], visited | {neighbor})

        for node in sorted(imports_map.keys()):
            dfs(node, node, [node], {node})

        return cycles

    def _format_workspace_graph_report(self, graph: Dict[str, Any]) -> str:
        """Formats a full workspace dependency topology map."""
        all_files = graph["files"]
        total_links = sum(len(deps) for deps in graph["imports"].values())

        # Collect unique external packages
        all_external: Dict[str, int] = {}
        for pkgs in graph["external_packages"].values():
            for p in pkgs:
                all_external[p] = all_external.get(p, 0) + 1

        # Determine Entry Points: files with 0 incoming dependencies
        entry_points = [f for f in all_files if not graph["dependents"].get(f)]

        lines = [
            "=============================================================================",
            "[WORKSPACE DEPENDENCY TOPOLOGY MAP]",
            "=============================================================================",
            f"Total Source Files: {len(all_files)} | Internal Dependency Links: {total_links} | External Packages: {len(all_external)}",
            "",
            f"🚀 ENTRY POINTS (Modules not imported by any other file - {len(entry_points)}):",
        ]
        if entry_points:
            for ep in sorted(entry_points):
                deps = graph["imports"].get(ep, [])
                if deps:
                    lines.append(f"  • {ep}")
                    for d in deps:
                        lines.append(f"    └── imports: {d}")
                else:
                    lines.append(f"  • {ep} (Standalone)")
        else:
            lines.append("  (None detected)")

        lines.extend([
            "",
            "📦 MODULE DEPENDENCY HIERARCHY:",
        ])
        # Files that are imported by other files
        connected_files = [f for f in all_files if graph["dependents"].get(f) or graph["imports"].get(f)]
        for f in sorted(connected_files):
            deps = graph["imports"].get(f, [])
            importers = graph["dependents"].get(f, [])
            lines.append(f"  • {f}")
            if deps:
                lines.append(f"    ├── imports ({len(deps)}): {', '.join(deps)}")
            if importers:
                lines.append(f"    └── imported by ({len(importers)}): {', '.join(importers)}")

        if all_external:
            lines.extend([
                "",
                f"🌐 EXTERNAL PACKAGES USED ({len(all_external)}):",
            ])
            for pkg, count in sorted(all_external.items()):
                lines.append(f"  • {pkg} ({count} file{'s' if count != 1 else ''})")

        # Detect circular dependencies using graph DFS
        circulars = self._detect_circular_dependencies(graph["imports"])

        if circulars:
            lines.extend([
                "",
                "⚠️ CIRCULAR DEPENDENCIES DETECTED:",
            ])
            for c in circulars:
                lines.append(f"  • {c}")

        lines.append("=============================================================================")
        return "\n".join(lines)
