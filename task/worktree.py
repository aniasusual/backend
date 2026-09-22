"""
Git worktree sandboxing for isolated subagent execution.
Replicates Oh My Pi's task/worktree.ts and task/isolation-runner.ts.

Provides temporary, isolated workspace branches so subagents can perform
edits, builds, or tests without polluting the primary working tree until verified.
"""

import logging
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def is_git_repo(path: Path) -> bool:
    """Check if a directory is inside a valid git repository."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(path),
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def sanitize_branch_name(raw_name: str) -> str:
    """Sanitize arbitrary agent IDs into valid Git branch name components."""
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "subagent"


def prepare_isolation_worktree(
    project_root: Path,
    agent_id: str,
) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    """
    Create a detached Git worktree for isolated subagent execution.
    Returns (worktree_path, branch_name, error_message).
    """
    if not is_git_repo(project_root):
        return None, None, f"Directory '{project_root}' is not a valid Git repository. Cannot create worktree."

    clean_id = sanitize_branch_name(agent_id)
    unique_suffix = uuid.uuid4().hex[:6]
    branch_name = f"lowkey-worktree-{clean_id}-{unique_suffix}"
    temp_dir = Path(tempfile.mkdtemp(prefix=f"lowkey_wt_{clean_id}_"))

    try:
        # Create worktree with a dedicated branch
        cmd = ["git", "worktree", "add", "-b", branch_name, str(temp_dir), "HEAD"]
        res = subprocess.run(cmd, cwd=str(project_root), capture_output=True, text=True, check=False)
        if res.returncode != 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, None, f"git worktree add failed: {res.stderr.strip()}"

        return temp_dir, branch_name, None
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, None, f"Exception creating worktree: {str(e)}"


def capture_worktree_patch(worktree_path: Path) -> Tuple[str, Optional[str]]:
    """
    Capture all uncommitted changes (modified, deleted, AND newly created untracked files)
    in the worktree as a unified Git diff/patch.
    Returns (patch_content, error_message).
    """
    try:
        # 1. Stage untracked files as intent-to-add so git diff HEAD includes new files
        subprocess.run(
            ["git", "add", "-N", "."],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            check=False,
        )

        # 2. Check diff against HEAD
        res = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=str(worktree_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return "", f"git diff failed: {res.stderr.strip()}"
        return res.stdout, None
    except Exception as e:
        return "", f"Failed to capture patch: {str(e)}"


def apply_patch_to_root(project_root: Path, patch_text: str) -> Tuple[bool, Optional[str]]:
    """
    Apply a unified diff patch to the main project repository.
    Returns (success, error_message).
    """
    if not patch_text.strip():
        return True, None

    try:
        # Check if patch applies cleanly
        check_res = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=patch_text,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if check_res.returncode != 0:
            return False, f"Patch cannot be applied cleanly: {check_res.stderr.strip()}"

        # Apply patch
        apply_res = subprocess.run(
            ["git", "apply", "-"],
            input=patch_text,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if apply_res.returncode != 0:
            return False, f"git apply failed: {apply_res.stderr.strip()}"

        return True, None
    except Exception as e:
        return False, f"Exception applying patch: {str(e)}"


def cleanup_isolation_worktree(
    project_root: Path,
    worktree_path: Path,
    branch_name: Optional[str] = None,
) -> Optional[str]:
    """
    Remove the temporary worktree, delete its isolated branch, and prune worktrees.
    """
    try:
        # 1. Remove git worktree
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )

        # 2. Prune any stale administrative entries
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            check=False,
        )

        # 3. Clean up directory if still exists
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        # 4. Delete temporary branch if specified
        if branch_name:
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                check=False,
            )

        return None
    except Exception as e:
        return f"Error cleaning up worktree: {str(e)}"


class WorktreeToolRegistryProxy:
    """
    Proxies a ToolRegistry so that file operations and command executions
    operate within an isolated Git worktree directory instead of the root sandbox.
    """

    def __init__(self, base_registry: Any, worktree_path: Path):
        self._base = base_registry
        self.sandbox_path = worktree_path.resolve()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)

    def _resolve_worktree_path(self, file_path: str) -> Path:
        return (self.sandbox_path / file_path).resolve()

    def _read_file_scoped(self, file_path: Optional[str] = None, start_line: int = 1, end_line: Optional[int] = None) -> str:
        if not file_path:
            return "Error: file_path is required"
        target = self._resolve_worktree_path(file_path)
        if not target.exists():
            return f"Error: File '{file_path}' not found in worktree."
        try:
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
            start_idx = max(0, start_line - 1)
            end_idx = end_line if end_line is not None else len(lines)
            selected = lines[start_idx:end_idx]
            numbered = [f"{start_idx + i + 1}: {l}" for i, l in enumerate(selected)]
            return "\n".join(numbered)
        except Exception as e:
            return f"Error reading file '{file_path}': {str(e)}"

    def _write_file_scoped(self, file_path: str, content: str) -> str:
        target = self._resolve_worktree_path(file_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} characters to '{file_path}' in worktree."
        except Exception as e:
            return f"Error writing file '{file_path}': {str(e)}"

    def _edit_file_scoped(self, file_path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
        target = self._resolve_worktree_path(file_path)
        if not target.exists():
            return f"Error: File '{file_path}' not found in worktree."
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            if old_text not in content:
                return f"Error: old_text not found in '{file_path}'."
            if replace_all:
                updated = content.replace(old_text, new_text)
            else:
                updated = content.replace(old_text, new_text, 1)
            target.write_text(updated, encoding="utf-8")
            return f"Successfully edited '{file_path}' in worktree."
        except Exception as e:
            return f"Error editing file '{file_path}': {str(e)}"

    def _glob_files_scoped(self, pattern: str, path: str = ".") -> str:
        base_dir = self._resolve_worktree_path(path)
        if not base_dir.exists():
            return f"Directory '{path}' not found."
        try:
            matches = [str(p.relative_to(self.sandbox_path)) for p in base_dir.glob(pattern)]
            return "\n".join(sorted(matches)) if matches else "No matching files found."
        except Exception as e:
            return f"Error globbing: {str(e)}"

    def _execute_command_scoped(self, command: str, reason: str = "") -> str:
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=str(self.sandbox_path),
                capture_output=True,
                text=True,
                check=False,
            )
            out = res.stdout.strip()
            err = res.stderr.strip()
            output = out
            if err:
                output += f"\n[stderr]\n{err}"
            return output or "(command completed with no output)"
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def get_tools(self) -> Dict[str, Callable]:
        tools = dict(self._base.get_tools()) if hasattr(self._base, "get_tools") else {}
        tools["read_file"] = self._read_file_scoped
        tools["write_file"] = self._write_file_scoped
        tools["edit_file"] = self._edit_file_scoped
        tools["glob_files"] = self._glob_files_scoped
        tools["execute_command"] = self._execute_command_scoped
        return tools

