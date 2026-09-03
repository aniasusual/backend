import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple


class LinterTools:
    """
    Dedicated handler for static syntax checks and linting across JavaScript,
    JSX, TypeScript, and JSON files before code changes are committed or tested.
    """

    def __init__(self, sandbox_path: Path, is_safe_path_fn: Callable[[str], bool]):
        self.sandbox_path = sandbox_path
        self._is_safe_path = is_safe_path_fn

    def lint_javascript(self, file_path: str = ".") -> str:
        """Run a static syntax and import validation check on JavaScript/JSX/TypeScript files.

        Args:
            file_path: The relative path to the file or directory to lint (e.g. 'src/App.jsx', 'server/index.js').

        Returns:
            A formatted diagnostic report indicating syntax validity or exact line/column errors.
        """
        if not file_path or not file_path.strip():
            file_path = "."

        if not self._is_safe_path(file_path):
            return f"Error: Access denied to path outside sandbox: {file_path}"

        target = (self.sandbox_path / file_path).resolve()
        if not target.exists():
            return f"Error: Target path does not exist: {file_path}"

        files_to_lint: List[Path] = []
        ignore_dirs = {".git", "node_modules", "dist", "build", "venv", ".next", "__pycache__"}

        if target.is_file():
            files_to_lint.append(target)
        else:
            for item in target.rglob("*"):
                if any(d in item.parts for d in ignore_dirs):
                    continue
                if item.is_file() and item.suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
                    files_to_lint.append(item)

        if not files_to_lint:
            return f"No JavaScript/TypeScript files found to lint at '{file_path}'."

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
