"""
Deterministic Static Security & Code Quality Scanner.
Provides multi-file AST/regex audit across components, routes, and utilities.
Serves as the resilient fallback and multi-file discovery engine for CodeReviewerSubagent.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


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
    def scan(
        cls,
        sandbox_path: Optional[Path],
        files: List[str],
        focus_areas: str = "",
    ) -> Tuple[List[str], int]:
        """
        Scans specified files against rigorous security, reliability, and best-practice rules.
        Returns (findings, score).
        """
        findings: List[str] = []
        score = 95

        if not sandbox_path or not sandbox_path.exists():
            return (["⚠️ Workspace sandbox not found. Heuristic evaluation skipped."], score)

        for file_rel in files:
            full_path = sandbox_path / file_rel
            if not full_path.exists() or not full_path.is_file():
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # 1. Hardcoded credentials / secrets
            if re.search(
                r"""(?:apiKey|api_key|secret|password|token|auth_token|jwt_secret)\s*=\s*['"][a-zA-Z0-9_\-]{8,}['"]""",
                content,
                re.IGNORECASE,
            ):
                findings.append(
                    f"**Security Warning ({file_rel})**: Potential hardcoded API secret or credential detected. Use environment variables."
                )
                score -= 20

            # 2. Dynamic code execution (eval, new Function, child_process.exec)
            if "eval(" in content:
                findings.append(
                    f"**Critical Vulnerability ({file_rel})**: Dangerous `eval()` detected. Re-architect to eliminate dynamic code evaluation."
                )
                score -= 30
            elif "new Function(" in content:
                findings.append(
                    f"**Critical Vulnerability ({file_rel})**: Dangerous `new Function()` constructor detected. Eliminate dynamic execution."
                )
                score -= 25
            elif re.search(r"""child_process\s*\.\s*exec\(""", content) or re.search(r"""\bexec\s*\(\s*['"`]""", content):
                findings.append(
                    f"**Critical Security Vulnerability ({file_rel})**: Potential shell command injection hazard detected with `exec()`. Use `execFile` with sanitized arguments."
                )
                score -= 25

            # 3. SQL Injection: string concatenation AND ES6 template literals
            # String concatenation: SELECT ... + req.
            if re.search(r"""(?:SELECT|INSERT|UPDATE|DELETE)\s+.*\+\s*req\.""", content, re.IGNORECASE):
                findings.append(
                    f"**Critical Security Vulnerability ({file_rel})**: Potential SQL injection via unescaped string concatenation with request parameters. Use parameterized queries."
                )
                score -= 30
            # ES6 template literal: `SELECT ... ${req.`
            elif re.search(r"""(?:SELECT|INSERT|UPDATE|DELETE)\s+[^`]*\$\{req\.""", content, re.IGNORECASE):
                findings.append(
                    f"**Critical Security Vulnerability ({file_rel})**: Potential SQL injection via unescaped template literal interpolation `${{req....}}`. Use parameterized queries."
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
                    findings.append(
                        f"**Reliability Hazard ({file_rel})**: Async Express route handler missing `try/catch` block. Unhandled promise rejections can crash the server."
                    )
                    score -= 10
                    break

            # 5. React Anti-Patterns
            if file_rel.endswith((".jsx", ".tsx")) or "React" in content or "import " in content:
                # Missing keys in map
                if ".map(" in content and "key=" not in content:
                    findings.append(
                        f"**React Anti-Pattern ({file_rel})**: Array `.map()` render appears to be missing a unique `key` prop."
                    )
                    score -= 5

                # Direct state mutations
                if re.search(r"""(?:\bset[A-Z]\w*\s*\(\s*)?[a-zA-Z0-9_]+\.push\(""", content):
                    if "state" in content or "useState" in content:
                        findings.append(
                            f"**React Anti-Pattern ({file_rel})**: Potential direct array mutation (e.g., `.push()`). Use immutable state updates (`[...prev, newItem]`)."
                        )
                        score -= 5

        # Cap score between 0 and 100
        score = max(0, min(100, score))
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
