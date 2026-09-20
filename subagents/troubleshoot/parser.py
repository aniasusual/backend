"""
Stack Trace Parser & Deterministic Error Classifier for TroubleshootSubagent.
Handles ANSI stripping, multi-platform stack traces (Node, Vite, Python, Vitest),
and disambiguates 3rd-party npm packages from local relative component imports.
"""

from pathlib import Path
import re
from typing import Optional


class StackTraceParser:
    """Parses raw error logs and extracts structured crash locations and fast-path fixes."""

    ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    @classmethod
    def strip_ansi(cls, text: str) -> str:
        """Strips ANSI terminal color codes from error logs."""
        if not text:
            return ""
        return cls.ANSI_ESCAPE_RE.sub("", text)

    @classmethod
    def _normalize_path(cls, path_str: str, line: str = "") -> str:
        """Normalizes path by cleaning slashes and stripping leading workspace/system prefixes."""
        clean_path = path_str.replace("\\", "/").lstrip("/")
        parts = clean_path.split("/")

        # If absolute system path, keep relative part starting from the nearest project folder marker
        common_markers = ["src", "server", "frontend", "backend", "client", "api", "app", "lib", "components", "pages", "routes"]
        for marker in common_markers:
            if marker in parts:
                clean_path = "/".join(parts[parts.index(marker):])
                break
        else:
            # Fall back to retaining at most the last 3 path segments if deeply nested
            if len(parts) > 3:
                clean_path = "/".join(parts[-3:])

        return f"{clean_path}:{line}" if line else clean_path

    @classmethod
    def extract_file_location(cls, log: str, fallback_file: str = "") -> str:
        """
        Extracts a relative file path and line number hint (e.g. 'src/App.jsx:42')
        from stack traces across Node, Vite, Vitest, and Python.
        Uses generalized regex patterns without hardcoding specific directory structures.
        """
        if not log:
            return fallback_file

        clean = cls.strip_ansi(log)

        # 1. Vitest / Jest pointer: ❯ path/to/file.ext:12:4
        vitest_match = re.search(
            r"[❯>]\s*([^\s:()\[\]]+\.(?:jsx|tsx|js|ts|mjs|cjs|py)):(\d+)(?::\d+)?",
            clean,
        )
        if vitest_match:
            return cls._normalize_path(vitest_match.group(1), vitest_match.group(2))

        # 2. Python traceback: File "...", line 42
        py_match = re.search(
            r'File\s+["\']([^"\']+\.py)["\'],\s+line\s+(\d+)',
            clean,
        )
        if py_match:
            return cls._normalize_path(py_match.group(1), py_match.group(2))

        # 3. file:/// URI in ES modules or Node stack traces:
        # e.g. at file:///path/to/server/routes/api.js:42:15
        file_uri_match = re.search(
            r"file://(?:localhost)?(/?[^\s:()\[\]]+\.(?:jsx|tsx|js|ts|mjs|cjs|py)):(\d+)(?::\d+)?",
            clean,
        )
        if file_uri_match:
            return cls._normalize_path(file_uri_match.group(1), file_uri_match.group(2))

        # 4. Standard JS/TS/Node/Vite stack frames:
        # e.g. "at App (/path/to/src/App.jsx:42:15)" or "at components/Header.jsx:12:4"
        frame_match = re.search(
            r"(?:at\s+(?:[^\n(]*\()?)?([a-zA-Z0-9_\-./\\]+\.(?:jsx|tsx|js|ts|mjs|cjs|py)):(\d+)(?::\d+)?\)?",
            clean,
        )
        if frame_match:
            raw_path = frame_match.group(1)
            line = frame_match.group(2)
            if not raw_path.startswith("node:") and "node_modules" not in raw_path:
                return cls._normalize_path(raw_path, line)

        # 5. Generic file match without line number
        generic_match = re.search(r"([a-zA-Z0-9_\-./\\]+\.(?:jsx|tsx|js|ts|mjs|cjs|py))", clean)
        if generic_match:
            raw_path = generic_match.group(1)
            if not raw_path.startswith("node:") and "node_modules" not in raw_path:
                return cls._normalize_path(raw_path, "")

        return fallback_file

    @classmethod
    def classify_fast_path(cls, log: str) -> Optional[str]:
        """
        Identifies deterministic environmental and configuration errors, returning an instant RCA.
        Returns None if the issue requires deep code investigation.
        """
        clean_log = cls.strip_ansi(log).strip()

        # 1. Missing Import / Module Resolution
        missing_mod_match = re.search(
            r"(?:Cannot find module|Failed to resolve import|Module not found: Error: Can't resolve) ['\"]([^'\"]+)['\"]",
            clean_log,
        )
        if missing_mod_match:
            specifier = missing_mod_match.group(1).strip()

            # Disambiguate local file vs 3rd-party npm package
            is_local = (
                specifier.startswith(("./", "../", "/", "@/"))
                or any(specifier.endswith(ext) for ext in [".jsx", ".tsx", ".js", ".ts", ".css", ".json", ".svg"])
            )

            if is_local:
                return f"""### 🩺 Root Cause Analysis (RCA): Missing Local File / Component
- **Issue**: The application is attempting to import `{specifier}`, but the file was not found in the workspace.
- **Root Cause**: Missing, renamed, or mistyped local component file.
- **Recommended Fix**:
  1. Use `glob_files(pattern="*{Path(specifier).stem}*")` or `list_directory` to verify the actual location and casing.
  2. If the component has not yet been built, create it using `write_file(file_path="...", content="...")`.
  3. Ensure the relative import path in the caller file matches the exact casing and extension."""

            # 3rd-Party NPM Dependency
            pkg_name = specifier
            if "/" in pkg_name and not pkg_name.startswith("@"):
                pkg_name = pkg_name.split("/")[0]
            elif pkg_name.startswith("@") and pkg_name.count("/") > 1:
                parts = pkg_name.split("/")
                pkg_name = f"{parts[0]}/{parts[1]}"

            return f"""### 🩺 Root Cause Analysis (RCA): Missing Dependency
- **Issue**: The application is attempting to import `{pkg_name}`, but the package is not installed in `node_modules`.
- **Root Cause**: Missing NPM dependency.
- **Recommended Fix**:
  Execute the following command to install the missing package:
  ```bash
  execute_command(command="npm install {pkg_name}", reason="Install missing dependency {pkg_name}")
  ```
- **Next Steps**: Vite HMR will automatically detect the installed package."""

        # 2. Port Conflict (EADDRINUSE)
        port_match = re.search(
            r"EADDRINUSE.*?port (\d+)|listen EADDRINUSE: address already in use (?::::|0\.0\.0\.0:)?(\d+)",
            clean_log,
            re.IGNORECASE,
        )
        if port_match:
            port = port_match.group(1) or port_match.group(2) or "3000"
            return f"""### 🩺 Root Cause Analysis (RCA): Port Conflict
- **Issue**: Port `{port}` is already in use by another active process.
- **Root Cause**: `EADDRINUSE` collision. A previous server process is still occupying port `{port}`.
- **Recommended Fix**:
  1. Ensure the Express backend server listens dynamically on `process.env.BACKEND_PORT || 5001`.
  2. Inspect active processes using `execute_command(command="lsof -i :{port}")` to identify and terminate orphaned processes if needed."""

        # 3. CORS Error
        if any(w in clean_log for w in ["CORS", "Access-Control-Allow-Origin", "blocked by CORS policy"]):
            return """### 🩺 Root Cause Analysis (RCA): CORS Security Block
- **Issue**: Browser blocked a cross-origin API request between frontend and backend.
- **Root Cause**: Backend server missing CORS middleware or headers for the active frontend origin.
- **Recommended Fix**:
  In your backend server (`server/index.js`), ensure CORS middleware is configured:
  ```javascript
  import cors from 'cors';
  app.use(cors({ origin: true, credentials: true }));
  ```
  And install cors if needed: `execute_command(command="npm install cors", reason="Install cors middleware")`."""

        return None
