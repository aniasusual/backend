"""
Stack Trace Parser & Deterministic Error Classifier for TroubleshootSubagent.
Handles ANSI stripping, multi-platform stack traces (Node, Vite, Python, Vitest),
and disambiguates 3rd-party npm packages from local relative component imports.
"""

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
    def extract_file_location(cls, log: str, fallback_file: str = "") -> str:
        """
        Extracts the relative file path and line number (e.g. src/App.jsx:42)
        from stack traces across Node, Vite, Vitest, and Python.
        """
        if not log:
            return fallback_file

        clean = cls.strip_ansi(log)

        # 1. Vitest / Jest symbol pointer: ❯ src/components/Header.jsx:12:4
        vitest_match = re.search(
            r"[❯>]\s*([a-zA-Z0-9_\-/\\]+\.(?:jsx|tsx|js|ts|py)):(\d+)(?::\d+)?",
            clean,
        )
        if vitest_match:
            return f"{vitest_match.group(1).replace('\\', '/')}:{vitest_match.group(2)}"

        # 2. Node / Vite / Webpack stack traces:
        # e.g. "at App (src/App.jsx:42:15)" or "at src/components/Header.jsx:12:4"
        node_match = re.search(
            r"(?:at [^\n]*\()?((?:src|server|components|pages|utils|app|lib|routes)/[a-zA-Z0-9_\-/\\]+\.[a-zA-Z0-9]+):(\d+)(?::\d+)?\)?",
            clean,
        )
        if node_match:
            return f"{node_match.group(1).replace('\\', '/')}:{node_match.group(2)}"

        # 3. Python stack traces: File ".../server.py", line 42, in ...
        py_match = re.search(
            r'File\s+["\']([^"\']+\.py)["\'],\s+line\s+(\d+)',
            clean,
        )
        if py_match:
            file_path = py_match.group(1).replace("\\", "/")
            # If absolute, retain relative part if inside src or server
            for prefix in ["src/", "server/", "backend/", "app/"]:
                if prefix in file_path:
                    file_path = file_path[file_path.index(prefix):]
                    break
            else:
                file_path = file_path.split("/")[-1]
            return f"{file_path}:{py_match.group(2)}"

        # 4. Vite compiler direct location: /src/App.jsx:42:15
        vite_direct = re.search(
            r"(?:^|\s|\()/?((?:src|server)/[a-zA-Z0-9_\-/\\]+\.[a-zA-Z0-9]+):(\d+)(?::\d+)?",
            clean,
            re.MULTILINE,
        )
        if vite_direct:
            return f"{vite_direct.group(1).replace('\\', '/')}:{vite_direct.group(2)}"

        # 5. Generic file match without line number
        match_generic = re.search(r"((?:src|server)/[a-zA-Z0-9_\-/\\]+\.[a-zA-Z0-9]+)", clean)
        if match_generic:
            return match_generic.group(1).replace("\\", "/")

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
  1. Verify whether the component exists under `src/components/` or the expected path.
  2. If the component has not yet been built, create it using `write_file(file_path="...", content="...")`.
  3. Ensure the relative import path in the caller file matches the exact casing and file extension."""

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
- **Next Steps**: After installation, restart the dev server with `run_background_command(command="npm run dev")`."""

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
- **Root Cause**: `EADDRINUSE` collision. A previous server or dev instance is still occupying port `{port}`.
- **Recommended Fix**:
  1. If you have an active background PID, stop it using:
     `stop_background_command(pid=...)`
  2. Or start Vite on the next available port:
     `run_background_command(command="npm run dev -- --port {int(port) + 1}", reason="Start server on alternate port")`"""

        # 3. CORS Error
        if any(w in clean_log for w in ["CORS", "Access-Control-Allow-Origin", "blocked by CORS policy"]):
            return """### 🩺 Root Cause Analysis (RCA): CORS Security Block
- **Issue**: Browser blocked a cross-origin API request between frontend and backend.
- **Root Cause**: Backend server missing CORS middleware or headers for `http://localhost:3000` (or `5173`).
- **Recommended Fix**:
  In your backend server (`server/index.js`), ensure CORS middleware is configured:
  ```javascript
  import cors from 'cors';
  app.use(cors({ origin: '*', credentials: true }));
  ```
  And install cors if needed: `execute_command(command="npm install cors")`."""

        return None
