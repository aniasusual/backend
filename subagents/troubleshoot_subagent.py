import re
from pathlib import Path
from typing import Dict, Any, Optional, List

from subagents.base import BaseSubagent


class TroubleshootSubagent(BaseSubagent):
    """
    Specialized Diagnostic and Root Cause Analysis (RCA) Subagent.
    Inspired by Emergent's troubleshoot_agent_sonnet_4_5.
    Parses compiler logs, stack traces, runtime exceptions, and port conflicts
    to produce surgical, actionable code fixes.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = "qwen2.5-coder:7b",
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            sandbox_path=sandbox_path,
            model_name=model_name,
            tool_registry=tool_registry,
            event_callback=event_callback,
            **kwargs,
        )


    def diagnose_error(
        self,
        error_log: str,
        context_file: str = "",
        recent_actions: str = "",
    ) -> str:
        """
        Performs Root Cause Analysis (RCA) on error logs or stack traces.
        Identifies failing files, exact line numbers, and actionable resolution steps.
        """
        if not error_log or not error_log.strip():
            return "Error: error_log parameter must not be empty."

        clean_log = error_log.strip()

        # 1. Check for Missing Dependency / Package
        missing_mod_match = re.search(r"(?:Cannot find module|Failed to resolve import|Module not found: Error: Can't resolve) ['\"]([^'\"]+)['\"]", clean_log)
        if missing_mod_match:
            pkg_name = missing_mod_match.group(1)
            # Normalize scoped package or subpath (e.g. 'lucide-react/dist' -> 'lucide-react')
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

        # 2. Check for Port Conflict (EADDRINUSE)
        port_match = re.search(r"EADDRINUSE.*?port (\d+)|listen EADDRINUSE: address already in use (?::::|0\.0\.0\.0:)?(\d+)", clean_log, re.IGNORECASE)
        if port_match:
            port = port_match.group(1) or port_match.group(2) or "3000"
            return f"""### 🩺 Root Cause Analysis (RCA): Port Conflict
- **Issue**: Port `{port}` is already in use by another active process.
- **Root Cause**: `EADDRINUSE` collision. A previous server instance is still occupying port `{port}`.
- **Recommended Fix**:
  1. If you have an active background PID, stop it using:
     `stop_background_command(pid=...)`
  2. Or start Vite on the next available port:
     `run_background_command(command="npm run dev -- --port {int(port) + 1}", reason="Start server on alternate port")`"""

        # 3. Check for CORS Error
        if "CORS" in clean_log or "Access-Control-Allow-Origin" in clean_log or "blocked by CORS policy" in clean_log:
            return """### 🩺 Root Cause Analysis (RCA): CORS Security Block
- **Issue**: Browser blocked a cross-origin API request between frontend and backend.
- **Root Cause**: Backend server missing CORS middleware or headers for `http://localhost:3000` (or `5173`).
- **Recommended Fix**:
  In your backend server (`server.js` or `app.js`), ensure CORS middleware is configured:
  ```javascript
  import cors from 'cors';
  app.use(cors({ origin: '*', credentials: true }));
  ```
  And install cors: `npm install cors`."""

        # 4. Check for React Undefined / TypeError Runtime Exceptions
        undefined_match = re.search(r"TypeError: Cannot read propert(?:y|ies) of (?:null|undefined) \(reading ['\"]?([^'\")]+)['\"]?\)", clean_log)
        if undefined_match:
            prop_name = undefined_match.group(1)
            file_loc = self._extract_file_location(clean_log, context_file)
            loc_str = f" in `{file_loc}`" if file_loc else ""

            return f"""### 🩺 Root Cause Analysis (RCA): Unhandled Null/Undefined Reference
- **Issue**: Attempted to access property `.{prop_name}` on a `null` or `undefined` object{loc_str}.
- **Root Cause**: Asynchronous state is accessed before data finishes loading or API response returns an empty structure.
- **Recommended Fix**:
  1. Add defensive optional chaining: Use `data?.{prop_name}` or `items?.{prop_name}` instead of direct property access.
  2. Add default fallback state: e.g. `const [{prop_name}List, set{prop_name.capitalize()}List] = useState([]);`
  3. Add loading state guard:
     ```jsx
     if (loading) return <div className="p-8 text-center text-muted">Loading data...</div>;
     ```"""

        # 5. Check for Vite / Rollup / JS Syntax Compilation Errors
        file_loc = self._extract_file_location(clean_log, context_file)
        syntax_match = re.search(r"(?:SyntaxError|Parse error|Unexpected token|Expected [^\n]+):? ([^\n]+)", clean_log)
        syntax_err = syntax_match.group(1) if syntax_match else "Syntax / Token validation failure"

        context_snippet = ""
        if file_loc and self.sandbox_path:
            clean_file_path = file_loc.split(":")[0]
            target_path = self.sandbox_path / clean_file_path
            if target_path.exists() and target_path.is_file():
                try:
                    lines = target_path.read_text(encoding="utf-8").splitlines()
                    line_no = int(file_loc.split(":")[1]) if ":" in file_loc else 1
                    start = max(0, line_no - 4)
                    end = min(len(lines), line_no + 3)
                    context_snippet = "\n**Code Context:**\n```jsx\n" + "\n".join(f"{i+1}: {lines[i]}" for i in range(start, end)) + "\n```\n"
                except Exception:
                    pass

        return f"""### 🩺 Root Cause Analysis (RCA): Code Compilation / Runtime Issue
- **Issue**: `{syntax_err}`
- **Failing Location**: `{file_loc if file_loc else 'Unknown file location'}`
{context_snippet}
- **Root Cause**: Invalid syntax, unclosed JSX tag, or malformed import statement.
- **Recommended Action**:
  1. Inspect `{file_loc if file_loc else 'the modified file'}` using `read_file`.
  2. Run `lint_javascript(file_path="...")` to verify syntax.
  3. Apply a surgical patch with `edit_file(file_path="...", old_text="...", new_text="...")`."""

    def _extract_file_location(self, log: str, fallback_file: str = "") -> str:
        """Extracts the file path and line number (e.g. src/App.jsx:42) from stack traces."""
        # Check standard Vite/Webpack stack trace pattern: (src/App.jsx:42:15) or /src/components/Header.jsx:12
        match = re.search(r"(?:at [^\n]*\()?((?:src|server|components|pages|utils|app)/[a-zA-Z0-9_\-/\.]+\.[a-zA-Z0-9]+):(\d+)(?::\d+)?\)?", log)
        if match:
            return f"{match.group(1)}:{match.group(2)}"

        match_generic = re.search(r"((?:src|server)/[a-zA-Z0-9_\-/\.]+\.[a-zA-Z0-9]+)", log)
        if match_generic:
            return match_generic.group(1)

        return fallback_file
