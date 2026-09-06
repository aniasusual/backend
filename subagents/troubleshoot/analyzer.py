"""
Intelligent Deterministic Static Fallback Analyzer for TroubleshootSubagent.
Provides rule-based classification and code context extraction for common
runtime exceptions (TypeErrors, ReferenceErrors, SyntaxErrors, React export mismatches)
when the LLM runner is offline.
"""

import re
from pathlib import Path
from typing import Optional, Tuple


class StaticTroubleshootAnalyzer:
    """Classifies runtime crash signatures and produces actionable deterministic RCAs."""

    @classmethod
    def analyze(
        cls,
        sandbox_path: Optional[Path],
        clean_log: str,
        file_loc: str,
    ) -> str:
        """Analyzes an error log and failing location to produce a structured RCA report."""
        clean_file_path = file_loc.split(":")[0] if file_loc else ""
        line_no = int(file_loc.split(":")[1]) if file_loc and ":" in file_loc else 1

        # Extract code snippet if file exists
        context_snippet = ""
        if clean_file_path and sandbox_path:
            target_path = sandbox_path / clean_file_path
            if target_path.exists() and target_path.is_file():
                try:
                    lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    start = max(0, line_no - 4)
                    end = min(len(lines), line_no + 3)
                    context_snippet = "\n**Code Context:**\n```jsx\n" + "\n".join(
                        f"{i+1:3d} | {lines[i]}" for i in range(start, end)
                    ) + "\n```\n"
                except Exception:
                    pass

        # 1. TypeError: Cannot read properties of undefined (reading 'xyz')
        undef_match = re.search(
            r"Cannot read properties of (?:undefined|null) \(reading ['\"]([^'\"]+)['\"]\)",
            clean_log,
        )
        if undef_match:
            prop = undef_match.group(1)
            return f"""### 🩺 Root Cause Analysis (RCA): Undefined Property Access
- **Issue**: Attempted to read property `.{prop}` on an undefined or null object.
- **Failing Location**: `{file_loc if file_loc else 'Unknown'}`
{context_snippet}
- **Root Cause**: The parent object is accessed before state initialization or before an async API response has resolved.
- **Recommended Surgical Fix**:
  1. Add optional chaining (`?.{prop}`) to safely guard undefined objects.
  2. Provide a safe initial state (e.g. `useState([])` instead of `useState()`) or a fallback default (`items?.{prop} || []`).
- **Instructions for Main Agent**: Call `edit_file(file_path="{clean_file_path or '...'}", old_text="...", new_text="...")` to guard the property access."""

        # 2. ReferenceError: X is not defined
        ref_match = re.search(r"([a-zA-Z0-9_$]+) is not defined", clean_log)
        if ref_match:
            symbol = ref_match.group(1)
            return f"""### 🩺 Root Cause Analysis (RCA): ReferenceError (Missing Import / Variable)
- **Issue**: Variable or hook `{symbol}` is not defined in scope.
- **Failing Location**: `{file_loc if file_loc else 'Unknown'}`
{context_snippet}
- **Root Cause**: `{symbol}` is being referenced without an import statement or local declaration.
- **Recommended Surgical Fix**:
  Ensure `{symbol}` is imported at the top of `{clean_file_path or 'the failing file'}`.
  ```javascript
  import {{ {symbol} }} from '...';
  ```
- **Instructions for Main Agent**: Call `edit_file` to add the missing import or variable declaration."""

        # 3. React.createElement: type is invalid (Default vs Named export mismatch)
        if "React.createElement: type is invalid" in clean_log or "Element type is invalid" in clean_log:
            return f"""### 🩺 Root Cause Analysis (RCA): React Component Import/Export Mismatch
- **Issue**: Element type is invalid; expected a string or class/function but got: `undefined`.
- **Failing Location**: `{file_loc if file_loc else 'Unknown'}`
{context_snippet}
- **Root Cause**: Mismatch between default and named exports (e.g. exporting `export default function Component` but importing with `import {{ Component }}`).
- **Recommended Surgical Fix**:
  Verify the export in the component file and align the import statement:
  - If default export: `import Component from './Component'`
  - If named export: `import {{ Component }} from './Component'`
- **Instructions for Main Agent**: Inspect the component file and correct the import statement using `edit_file`."""

        # 4. SyntaxError / Unexpected token
        if "SyntaxError" in clean_log or "Unexpected token" in clean_log:
            return f"""### 🩺 Root Cause Analysis (RCA): Syntax & Parser Error
- **Issue**: Syntax error or unclosed JSX token encountered during compilation.
- **Failing Location**: `{file_loc if file_loc else 'Unknown'}`
{context_snippet}
- **Root Cause**: Malformed JSX syntax, unclosed bracket/parenthesis, or misplaced operator.
- **Recommended Surgical Fix**:
  1. Inspect the code around line `{line_no}`.
  2. Run `lint_javascript(file_path="{clean_file_path or '...'}")` to pinpoint the exact token mismatch.
  3. Correct the syntax with `edit_file`."""

        # 5. Generic Runtime Failure
        return f"""### 🩺 Root Cause Analysis (RCA): Runtime / Compiler Issue
- **Issue**: Detected runtime or compiler failure.
- **Failing Location**: `{file_loc if file_loc else 'Unknown'}`
{context_snippet}
- **Root Cause**: Error log indicates an unhandled exception or malformed syntax.
- **Recommended Action**:
  1. Inspect `{file_loc if file_loc else 'the modified file'}` using `read_file`.
  2. Run `lint_javascript(file_path="{clean_file_path or '...'}")` to verify syntax.
  3. Apply a surgical patch using `edit_file`."""
