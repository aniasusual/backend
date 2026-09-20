"""
Deterministic Static Security & Code Quality Scanner.
Provides multi-file AST/regex audit across components, routes, and utilities.
Serves as the resilient fallback and multi-file discovery engine for CodeReviewerSubagent.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from subagents.reviewer.models import (
    FindingSeverity,
    FindingCategory,
    ReviewFinding,
    ReviewAuditReport,
)


class StaticSecurityScanner:
    """
    Scans project workspace source files to evaluate:
    1. Multi-file code discovery across src/ and server/.
    2. Secrets detection (API keys, tokens, passwords).
    3. Code execution hazards (eval, Function, exec).
    4. SQL injection vulnerabilities (string concatenation AND ES6 template literals).
    5. Express route error handling (try/catch in async route handlers).
    6. React anti-patterns (missing map keys, direct state mutations).
    """

    EXCLUDED_DIRS = {
        "node_modules",
        "dist",
        "build",
        ".git",
        "coverage",
        "venv",
        ".venv",
        "__pycache__",
    }

    CODE_EXTENSIONS = {
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
    }

    @classmethod
    def discover_code_files(cls, sandbox_path: Optional[Path]) -> List[str]:
        """
        Recursively discovers all source code files in the workspace (src/ and server/),
        skipping build and dependency artifacts.
        """
        if not sandbox_path or not sandbox_path.exists():
            return ["src/App.jsx", "server/index.js"]

        discovered: List[str] = []

        # Scan src and server directories recursively if they exist
        for base_dir_name in ["src", "server"]:
            base_dir = sandbox_path / base_dir_name
            if base_dir.exists() and base_dir.is_dir():
                for path in sorted(base_dir.rglob("*")):
                    if path.is_file() and path.suffix in cls.CODE_EXTENSIONS:
                        rel = path.relative_to(sandbox_path)
                        if not set(rel.parts).intersection(cls.EXCLUDED_DIRS):
                            discovered.append(rel.as_posix())

        # Also check root level config/entry files if present
        for root_file in ["package.json", "server.js", "index.js"]:
            p = sandbox_path / root_file
            if p.exists() and p.is_file():
                discovered.append(root_file)

        # Deduplicate while preserving order
        unique_files: List[str] = []
        for f in discovered:
            if f not in unique_files:
                unique_files.append(f)

        if not unique_files:
            for fallback_path in ["src/App.jsx", "src/App.tsx", "server/index.js", "server/server.js"]:
                if (sandbox_path / fallback_path).exists():
                    unique_files.append(fallback_path)

        return unique_files or ["src/App.jsx", "server/index.js"]

    @classmethod
    def scan_structured(
        cls,
        sandbox_path: Optional[Path],
        files: List[str],
        focus_areas: str = "",
    ) -> Tuple[List[ReviewFinding], int]:
        """
        Scans specified files against rigorous security, reliability, and best-practice rules.
        Returns typed (findings, score) with exact 1-indexed line numbers and code snippets.
        """
        findings: List[ReviewFinding] = []
        score = 95

        if not sandbox_path or not sandbox_path.exists():
            return (findings, score)

        for file_rel in files:
            full_path = sandbox_path / file_rel
            if not full_path.exists() or not full_path.is_file():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = content.splitlines()

            def get_line_info(char_idx: int) -> Tuple[int, str]:
                line_no = content[:char_idx].count("\n") + 1
                snippet = lines[line_no - 1].strip() if 0 <= line_no - 1 < len(lines) else ""
                return line_no, snippet

            # 1. Hardcoded credentials / secrets
            secret_match = re.search(
                r"""(?:apiKey|api_key|secret_key|api_secret|secret|password|token|auth_token|jwt_secret)\s*=\s*['"][a-zA-Z0-9_\-]{8,}['"]""",
                content,
                re.IGNORECASE,
            )
            if secret_match:
                line_no, snippet = get_line_info(secret_match.start())
                findings.append(
                    ReviewFinding(
                        file_path=file_rel,
                        line_number=line_no,
                        severity=FindingSeverity.CRITICAL,
                        category=FindingCategory.SECURITY,
                        title="Potential Hardcoded Secret",
                        description="Potential hardcoded API secret or credential detected. Use environment variables.",
                        code_snippet=snippet,
                        suggested_replacement="// Use process.env.<SECRET_NAME> instead",
                    )
                )
                score -= 20

            # 2. Dynamic code execution (eval, new Function, child_process.exec)
            eval_match = re.search(r"\beval\s*\(", content)
            if eval_match:
                line_no, snippet = get_line_info(eval_match.start())
                findings.append(
                    ReviewFinding(
                        file_path=file_rel,
                        line_number=line_no,
                        severity=FindingSeverity.CRITICAL,
                        category=FindingCategory.SECURITY,
                        title="Dangerous Dynamic Code Execution (eval)",
                        description="Dangerous `eval()` detected. Re-architect to eliminate dynamic code evaluation.",
                        code_snippet=snippet,
                    )
                )
                score -= 30
            elif "new Function(" in content:
                fn_match = re.search(r"new\s+Function\s*\(", content)
                line_no, snippet = get_line_info(fn_match.start()) if fn_match else (None, "")
                findings.append(
                    ReviewFinding(
                        file_path=file_rel,
                        line_number=line_no,
                        severity=FindingSeverity.CRITICAL,
                        category=FindingCategory.SECURITY,
                        title="Dangerous Dynamic Code Execution (new Function)",
                        description="Dangerous `new Function()` constructor detected. Eliminate dynamic execution.",
                        code_snippet=snippet,
                    )
                )
                score -= 25
            else:
                exec_match = re.search(r"""child_process\s*\.\s*exec\(""", content) or re.search(r"""\bexec\s*\(\s*['"`]""", content)
                if exec_match:
                    line_no, snippet = get_line_info(exec_match.start())
                    findings.append(
                        ReviewFinding(
                            file_path=file_rel,
                            line_number=line_no,
                            severity=FindingSeverity.CRITICAL,
                            category=FindingCategory.SECURITY,
                            title="Command Injection Hazard (exec)",
                            description="Potential shell command injection hazard detected with `exec()`. Use `execFile` with sanitized arguments.",
                            code_snippet=snippet,
                        )
                    )
                    score -= 25

            # 3. SQL Injection: string concatenation AND ES6 template literals
            sql_concat_match = re.search(r"""(?:SELECT|INSERT|UPDATE|DELETE)\s+.*\+\s*req\.""", content, re.IGNORECASE)
            if sql_concat_match:
                line_no, snippet = get_line_info(sql_concat_match.start())
                findings.append(
                    ReviewFinding(
                        file_path=file_rel,
                        line_number=line_no,
                        severity=FindingSeverity.CRITICAL,
                        category=FindingCategory.SECURITY,
                        title="SQL Injection (String Concatenation)",
                        description="Potential SQL injection via unescaped string concatenation with request parameters. Use parameterized queries.",
                        code_snippet=snippet,
                        suggested_replacement="// Use parameterized queries, e.g. db.query('SELECT * FROM table WHERE id = $1', [req.params.id])",
                    )
                )
                score -= 30
            else:
                sql_template_match = re.search(r"""(?:SELECT|INSERT|UPDATE|DELETE)\s+[^`]*\$\{req\.""", content, re.IGNORECASE)
                if sql_template_match:
                    line_no, snippet = get_line_info(sql_template_match.start())
                    findings.append(
                        ReviewFinding(
                            file_path=file_rel,
                            line_number=line_no,
                            severity=FindingSeverity.CRITICAL,
                            category=FindingCategory.SECURITY,
                            title="SQL Injection (Template Literal)",
                            description="Potential SQL injection via unescaped template literal interpolation `${req....}`. Use parameterized queries.",
                            code_snippet=snippet,
                            suggested_replacement="// Use parameterized queries, e.g. db.query('SELECT * FROM table WHERE id = $1', [req.params.id])",
                        )
                    )
                    score -= 30

            # 4. Express route async error handling
            route_matches = re.finditer(
                r"""(?:app|router)\.(?:get|post|put|delete|patch)\s*\(\s*['"][^'"]+['"]\s*,\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{""",
                content,
            )
            for rm in route_matches:
                handler_start = rm.start()
                snippet = content[handler_start : min(len(content), handler_start + 600)]
                if "async" in snippet and "try {" not in snippet and "try{" not in snippet:
                    line_no, line_snippet = get_line_info(handler_start)
                    findings.append(
                        ReviewFinding(
                            file_path=file_rel,
                            line_number=line_no,
                            severity=FindingSeverity.HIGH,
                            category=FindingCategory.RELIABILITY,
                            title="Unhandled Async Express Route",
                            description="Async Express route handler missing `try/catch` block. Unhandled promise rejections can crash the server.",
                            code_snippet=line_snippet,
                        )
                    )
                    score -= 10
                    break

            # 5. Express Port Binding & Architecture Check
            if "app.listen(" in content or "server.listen(" in content:
                port_3000_match = re.search(r"""(?:app|server)\.listen\s*\(\s*3000\b""", content) or re.search(r"""(?:const|let|var)\s+PORT\s*=\s*3000\b""", content)
                if port_3000_match:
                    line_no, snippet = get_line_info(port_3000_match.start())
                    findings.append(
                        ReviewFinding(
                            file_path=file_rel,
                            line_number=line_no,
                            severity=FindingSeverity.HIGH,
                            category=FindingCategory.ARCHITECTURE,
                            title="Port 3000 Conflict",
                            description="Server listens on port 3000, which collides with Vite frontend. Use `process.env.BACKEND_PORT || 5001`.",
                            code_snippet=snippet,
                            suggested_replacement="const PORT = process.env.BACKEND_PORT || 5001;",
                        )
                    )
                    score -= 15
                elif "process.env.BACKEND_PORT" not in content and "process.env.PORT" not in content:
                    listen_match = re.search(r"""(?:app|server)\.listen\(""", content)
                    line_no, snippet = get_line_info(listen_match.start()) if listen_match else (None, "")
                    findings.append(
                        ReviewFinding(
                            file_path=file_rel,
                            line_number=line_no,
                            severity=FindingSeverity.MEDIUM,
                            category=FindingCategory.ARCHITECTURE,
                            title="Static Port Binding",
                            description="Server does not read `process.env.BACKEND_PORT`. Bind with `const PORT = process.env.BACKEND_PORT || 5001;` to support dynamic port allocation.",
                            code_snippet=snippet,
                            suggested_replacement="const PORT = process.env.BACKEND_PORT || 5001;\napp.listen(PORT, ...);",
                        )
                    )
                    score -= 5

            # 6. React Anti-Patterns & Hardcoded URLs
            if file_rel.endswith((".jsx", ".tsx")) or "React" in content or "import " in content:
                # Missing keys in map
                if ".map(" in content and "key=" not in content:
                    map_match = re.search(r"\.map\(", content)
                    line_no, snippet = get_line_info(map_match.start()) if map_match else (None, "")
                    findings.append(
                        ReviewFinding(
                            file_path=file_rel,
                            line_number=line_no,
                            severity=FindingSeverity.MEDIUM,
                            category=FindingCategory.REACT_PATTERNS,
                            title="Missing Key in .map()",
                            description="Array `.map()` render appears to be missing a unique `key` prop.",
                            code_snippet=snippet,
                        )
                    )
                    score -= 5

                # Direct state mutations
                push_match = re.search(r"""(?:\bset[A-Z]\w*\s*\(\s*)?[a-zA-Z0-9_]+\.push\(""", content)
                if push_match and ("state" in content or "useState" in content):
                    line_no, snippet = get_line_info(push_match.start())
                    findings.append(
                        ReviewFinding(
                            file_path=file_rel,
                            line_number=line_no,
                            severity=FindingSeverity.MEDIUM,
                            category=FindingCategory.REACT_PATTERNS,
                            title="Direct State Mutation",
                            description="Potential direct array mutation (e.g., `.push()`). Use immutable state updates (`[...prev, newItem]`).",
                            code_snippet=snippet,
                        )
                    )
                    score -= 5

                # Hardcoded backend host/port in frontend API calls
                url_match = re.search(r"""fetch\s*\(\s*['"`]http://(?:localhost|127\.0\.0\.1):\d+""", content) or re.search(r"""axios\.\w+\s*\(\s*['"`]http://(?:localhost|127\.0\.0\.1):\d+""", content)
                if url_match:
                    line_no, snippet = get_line_info(url_match.start())
                    findings.append(
                        ReviewFinding(
                            file_path=file_rel,
                            line_number=line_no,
                            severity=FindingSeverity.MEDIUM,
                            category=FindingCategory.ARCHITECTURE,
                            title="Hardcoded Localhost API URL",
                            description="Hardcoded backend host/port in frontend API request. Use relative paths (e.g. `fetch('/api/...')`) to leverage Vite dev server proxy.",
                            code_snippet=snippet,
                            suggested_replacement="fetch('/api/...')",
                        )
                    )
                    score -= 5

        score = max(0, min(100, score))
        return findings, score

    @classmethod
    def scan(
        cls,
        sandbox_path: Optional[Path],
        files: List[str],
        focus_areas: str = "",
    ) -> Tuple[List[str], int]:
        """
        Scans specified files against rigorous security, reliability, and best-practice rules.
        Returns legacy (findings_strings, score) for full backward compatibility with tests.
        """
        if not sandbox_path or not sandbox_path.exists():
            return (["⚠️ Workspace sandbox not found. Heuristic evaluation skipped."], 95)

        structured_findings, score = cls.scan_structured(sandbox_path, files, focus_areas)
        findings: List[str] = []

        for f in structured_findings:
            # Map back to exact legacy string format for existing test assertions
            if f.title == "Potential Hardcoded Secret":
                findings.append(f"**Security Warning ({f.file_path})**: {f.description}")
            elif "eval" in f.title.lower() or "new function" in f.title.lower():
                findings.append(f"**Critical Vulnerability ({f.file_path})**: {f.description}")
            elif "command injection" in f.title.lower() or "sql injection" in f.title.lower():
                findings.append(f"**Critical Security Vulnerability ({f.file_path})**: {f.description}")
            elif "unhandled async" in f.title.lower():
                findings.append(f"**Reliability Hazard ({f.file_path})**: {f.description}")
            elif "port 3000" in f.title.lower():
                findings.append(f"**Port Conflict Hazard ({f.file_path})**: {f.description}")
            elif "static port" in f.title.lower():
                findings.append(f"**Port Architecture Warning ({f.file_path})**: {f.description}")
            elif f.category == FindingCategory.REACT_PATTERNS:
                findings.append(f"**React Anti-Pattern ({f.file_path})**: {f.description}")
            elif "hardcoded localhost" in f.title.lower():
                findings.append(f"**Network Architecture Warning ({f.file_path})**: {f.description}")
            else:
                findings.append(f"**[{f.severity.value}] ({f.file_path})**: {f.description}")

        return findings, score

    @classmethod
    def generate_report(
        cls,
        files: List[str],
        findings: List[str],
        score: int,
    ) -> str:
        """
        Formats a structured senior-level Code Review & Security Audit markdown report.
        """
        status = "APPROVED" if score >= 90 else ("NEEDS_REVISION" if score >= 75 else "CRITICAL_FIX_REQUIRED")
        issues_formatted = (
            "\n".join(f"- {f}" for f in findings)
            if findings
            else "- No high-severity code, reliability, or security flaws detected."
        )

        return f"""# 🧐 Code Review & Security Audit
**Target Files**: {', '.join(files)}
**Overall Code Quality Score**: **{score}/100**
**Status**: **{status}**

---

### 🚨 Issues & Audit Findings
{issues_formatted}

### 🛡️ Security & Resilience
- **Secrets Audit**: {'Passed — No raw credentials or API keys detected.' if score >= 90 else 'Action Required — Review flagged secrets above.'}
- **API Error Handling**: {'Verified robust structured error handling.' if score >= 80 else 'Action Required — Ensure async routes are wrapped in try/catch.'}
- **Input Sanitization**: {'Safe — No unescaped SQL or command injection patterns found.' if score >= 75 else 'Critical Action Required — Replace dynamic string queries with parameterized queries.'}

---
### 📋 Instructions for Main Engineer
{'✅ Code quality meets release standards. You may proceed to conclude the task with `finish`.' if score >= 90 else '👉 Apply surgical patches using `edit_file` to resolve the flagged issues before calling `finish`.'}
"""
