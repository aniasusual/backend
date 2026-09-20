import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Any


class LinterTools:
    """
    Dedicated handler for static syntax checks and linting across JavaScript,
    JSX, TypeScript, and JSON files before code changes are committed or tested.
    """

    def __init__(self, sandbox_path: Path, is_safe_path_fn: Callable[[str], bool]):
        self.sandbox_path = sandbox_path
        self._is_safe_path = is_safe_path_fn

    def lint_javascript(
        self,
        file_path: Optional[str] = ".",
        items: Optional[Any] = None,
        files: Optional[Any] = None,
        **kwargs: Any
    ) -> str:
        """Run a static syntax and import validation check on JavaScript/JSX/TypeScript files.

        Args:
            file_path: The relative path to the file or directory to lint (e.g. 'src/App.jsx', 'server/index.js').
            items: Optional list of file paths (or polymorphic item objects) to lint.
            files: Optional list of file paths to lint.
            **kwargs: Extra parameters ignored safely for robust LLM tool calling.

        Returns:
            A formatted diagnostic report indicating syntax validity or exact line/column errors.
        """
        paths_to_check: List[str] = []

        if isinstance(items, list) and items:
            for item in items:
                if isinstance(item, str) and item.strip():
                    paths_to_check.append(item.strip())
                elif isinstance(item, dict):
                    p = item.get("file_path") or item.get("path") or item.get("file")
                    if p and str(p).strip():
                        paths_to_check.append(str(p).strip())
        elif isinstance(items, str) and items.strip():
            paths_to_check.append(items.strip())

        if isinstance(files, list) and files:
            for item in files:
                if isinstance(item, str) and item.strip():
                    paths_to_check.append(item.strip())
                elif isinstance(item, dict):
                    p = item.get("file_path") or item.get("path") or item.get("file")
                    if p and str(p).strip():
                        paths_to_check.append(str(p).strip())
        elif isinstance(files, str) and files.strip():
            paths_to_check.append(files.strip())

        if not paths_to_check:
            if file_path and str(file_path).strip():
                paths_to_check.append(str(file_path).strip())
            else:
                paths_to_check.append(".")

        files_to_lint: List[Path] = []
        ignore_dirs = {".git", "node_modules", "dist", "build", "venv", ".next", "__pycache__"}

        for p in paths_to_check:
            if not self._is_safe_path(p):
                return f"Error: Access denied to path outside sandbox: {p}"

            target = (self.sandbox_path / p).resolve()
            if not target.exists():
                return f"Error: Target path does not exist: {p}"

            if target.is_file():
                if target not in files_to_lint:
                    files_to_lint.append(target)
            else:
                for item in target.rglob("*"):
                    if any(d in item.parts for d in ignore_dirs):
                        continue
                    if item.is_file() and item.suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
                        if item not in files_to_lint:
                            files_to_lint.append(item)

        if not files_to_lint:
            display_path = ", ".join(paths_to_check)
            return f"No JavaScript/TypeScript files found to lint at '{display_path}'."

        errors: List[str] = []
        checked_count = 0

        for file in files_to_lint:
            rel_file = str(file.relative_to(self.sandbox_path))
            checked_count += 1

            success, output = self._check_single_file(file, rel_file)
            if not success:
                errors.append(output)

        if errors:
            summary = f"❌ Found {len(errors)} syntax error(s) across {checked_count} file(s):\n\n"
            return summary + "\n\n".join(errors)

        return f"✅ No syntax errors found across {checked_count} file(s) ({', '.join(str(f.relative_to(self.sandbox_path)) for f in files_to_lint[:5])}{'...' if len(files_to_lint) > 5 else ''})."

    def _check_single_file(self, file_path: Path, rel_name: str) -> Tuple[bool, str]:
        """Runs fast syntax parsing on a single file using node --check or esbuild."""
        suffix = file_path.suffix.lower()

        # 1. Plain JavaScript (.js, .mjs, .cjs) without JSX can use node --check (ultra-fast <5ms)
        if suffix in {".js", ".mjs", ".cjs"}:
            try:
                res = subprocess.run(
                    ["node", "--check", str(file_path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if res.returncode == 0:
                    return True, ""
                # If node --check failed, check if it was due to JSX in a .js file or actual syntax error
                if "SyntaxError: Unexpected token '<'" in res.stderr:
                    # Treat as JSX and fall through to esbuild
                    pass
                else:
                    return False, f"[{rel_name}]\n{res.stderr.strip()}"
            except Exception:
                pass

        # 2. JSX / TSX / TS / Modern ES modules checked via esbuild
        try:
            res = subprocess.run(
                ["npx", "esbuild", str(file_path), "--format=esm"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0:
                return True, ""
            err_msg = res.stderr.strip() or res.stdout.strip()
            return False, f"[{rel_name}]\n{err_msg}"
        except subprocess.TimeoutExpired:
            return False, f"[{rel_name}]\nError: Syntax check timed out after 15 seconds."
        except Exception as e:
            return False, f"[{rel_name}]\nError running syntax checker: {str(e)}"
