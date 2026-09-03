"""
Lowkey Project Manager — Core business logic.

Handles creation, listing, deletion, and metadata management of user projects
stored under a fixed root directory (~/.lowkey/projects/).

All projects are fully independent — no global config, no shared state.
"""

from __future__ import annotations

import os
import re
import signal
import shutil
import platform
import subprocess
from pathlib import Path
from typing import List, Optional

from project_manager.models import ProjectInfo, _now_iso
from project_manager.template_manager import TemplateManager

try:
    from config.settings import PROJECTS_ROOT
except ImportError:
    PROJECTS_ROOT = Path(os.getenv("PROJECTS_ROOT", str(Path.home() / ".lowkey" / "projects"))).expanduser().resolve()

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

# Project name constraints
MAX_NAME_LENGTH = 50
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# ──────────────────────────────────────────────
# ProjectManager
# ──────────────────────────────────────────────

class ProjectManager:
    """
    Manages the lifecycle of user projects under ~/.lowkey/projects/.

    Each project is a subdirectory containing its own code and a
    .lowkey_meta.json metadata file. Projects are fully independent
    with no shared configuration.
    """

    def __init__(self, root: Optional[Path] = None, template_manager: Optional[TemplateManager] = None):
        """
        Args:
            root: Override the default projects root directory.
                  Useful for testing. Defaults to ~/.lowkey/projects/.
            template_manager: Optional custom TemplateManager instance.
        """
        self.root = (root or PROJECTS_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.template_manager = template_manager or TemplateManager()

    # ──────────────────────────────────────────
    # CRUD Operations
    # ──────────────────────────────────────────

    def create_project(self, name: str, template: str = "node_react") -> ProjectInfo:
        """
        Create a new project directory with metadata and scaffolded template files.

        Args:
            name: A kebab-case project name (e.g., "todo-app").
            template: The template to scaffold (default: "node_react").

        Returns:
            The created ProjectInfo.

        Raises:
            ValueError: If the name is invalid or already exists.
        """
        validated_name = self._validate_name(name)
        project_dir = self.root / validated_name

        if project_dir.exists():
            raise ValueError(
                f"Project '{validated_name}' already exists. "
                f"Use suggest_name('{validated_name}') to get an available name."
            )

        project_dir.mkdir(parents=True)

        # Scaffold template files (Express + React + Vite)
        if template:
            try:
                self.template_manager.scaffold_project(project_dir, template_name=template)
            except Exception as e:
                print(f"[ProjectManager] Template scaffolding error: {e}")

        project = ProjectInfo(
            name=validated_name,
            path=project_dir,
            template=template,
            status="stopped",
        )
        project.save_meta()

        return project

    def list_projects(self) -> List[ProjectInfo]:
        """
        List all projects under the root directory.

        Scans each subdirectory for a .lowkey_meta.json file,
        checks if any tracked processes are still alive,
        and returns a list sorted by last_opened (most recent first).
        """
        projects = []

        if not self.root.exists():
            return projects

        for entry in sorted(self.root.iterdir()):
            if not entry.is_dir():
                continue

            project = ProjectInfo.from_directory(entry)
            if project is None:
                # Directory exists but has no metadata — skip it
                continue

            # Resolve runtime status from stored PID
            project.status = self._resolve_status(project)
            if project.status == "stopped":
                # Clear stale runtime fields
                project.pid = None
                project.port = None

            projects.append(project)

        # Most recently opened first
        projects.sort(key=lambda p: p.last_opened, reverse=True)
        return projects

    def get_project(self, name: str) -> ProjectInfo:
        """
        Get a single project by name.

        Args:
            name: The project name.

        Returns:
            The ProjectInfo for the requested project.

        Raises:
            ValueError: If the project doesn't exist.
        """
        project_dir = self.root / name

        if not project_dir.exists():
            raise ValueError(f"Project '{name}' not found.")

        project = ProjectInfo.from_directory(project_dir)
        if project is None:
            raise ValueError(
                f"Directory '{name}' exists but has no valid metadata."
            )

        project.status = self._resolve_status(project)
        if project.status == "stopped":
            project.pid = None
            project.port = None

        return project

    def get_or_create_project(self, name: str, template: str = "node_react") -> ProjectInfo:
        """
        Get a project by name, or create it if it doesn't exist.
        If the directory exists but is missing metadata, the metadata will be recreated.
        """
        try:
            return self.get_project(name)
        except ValueError as e:
            if "not found" in str(e):
                return self.create_project(name, template=template)
            elif "no valid metadata" in str(e):
                validated_name = self._validate_name(name)
                project_dir = self.root / validated_name
                project = ProjectInfo(name=validated_name, path=project_dir, template=template)
                project.save_meta()
                return project
            raise
    def delete_project(self, name: str) -> None:
        """
        Delete a project: kill any running processes, then remove the directory.

        Args:
            name: The project name to delete.

        Raises:
            ValueError: If the project doesn't exist.
        """
        project = self.get_project(name)

        # Kill the tracked process if it's still running
        if project.pid and _is_process_alive(project.pid):
            _kill_process(project.pid)

        shutil.rmtree(project.path)

    def update_meta(self, name: str, **fields) -> ProjectInfo:
        """
        Update specific metadata fields for a project and persist them.

        Supported fields: last_opened, pid, port.

        Args:
            name: The project name.
            **fields: Key-value pairs of fields to update.

        Returns:
            The updated ProjectInfo.
        """
        project = self.get_project(name)

        for key, value in fields.items():
            if hasattr(project, key):
                setattr(project, key, value)

        project.save_meta()
        return project

    def touch_last_opened(self, name: str) -> ProjectInfo:
        """Update the last_opened timestamp to now."""
        return self.update_meta(name, last_opened=_now_iso())

    # ──────────────────────────────────────────
    # Name Helpers
    # ──────────────────────────────────────────

    def suggest_name(self, base_name: str) -> str:
        """
        Given a desired base name, return a unique name that doesn't collide
        with existing projects.

        Examples:
            suggest_name("todo-app")   → "todo-app"      (if available)
            suggest_name("todo-app")   → "todo-app-2"    (if "todo-app" exists)
            suggest_name("todo-app")   → "todo-app-3"    (if both exist)
        """
        slug = self._slugify(base_name)
        if not slug:
            slug = "untitled"

        # Truncate to max length, leaving room for a suffix like "-99"
        slug = slug[:MAX_NAME_LENGTH - 3]

        candidate = slug
        counter = 2
        while (self.root / candidate).exists():
            candidate = f"{slug}-{counter}"
            counter += 1

        return candidate

    # ──────────────────────────────────────────
    # OS Integration
    # ──────────────────────────────────────────

    def open_in_finder(self, name: str) -> None:
        """
        Open the project directory in the native file manager.

        Works on macOS (Finder), Windows (Explorer), and Linux (xdg-open).

        Raises:
            ValueError: If the project doesn't exist.
        """
        project = self.get_project(name)
        system = platform.system()

        if system == "Darwin":
            subprocess.Popen(["open", str(project.path)])
        elif system == "Windows":
            subprocess.Popen(["explorer", str(project.path)])
        else:
            # Linux / other Unix
            subprocess.Popen(["xdg-open", str(project.path)])

    # ──────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────

    def _validate_name(self, name: str) -> str:
        """
        Validate and normalize a project name.

        Rules:
            - Lowercase, kebab-case (letters, numbers, hyphens)
            - Cannot start or end with a hyphen
            - No consecutive hyphens
            - 1–50 characters

        Returns:
            The validated (lowercased) name.

        Raises:
            ValueError: If the name violates any rule.
        """
        if not name or not name.strip():
            raise ValueError("Project name cannot be empty.")

        name = name.strip().lower()

        if len(name) > MAX_NAME_LENGTH:
            raise ValueError(
                f"Project name must be {MAX_NAME_LENGTH} characters or fewer "
                f"(got {len(name)})."
            )

        if not NAME_PATTERN.match(name):
            raise ValueError(
                f"Invalid project name '{name}'. "
                f"Use lowercase letters, numbers, and single hyphens "
                f"(e.g., 'my-cool-app'). Cannot start/end with a hyphen."
            )

        return name

    @staticmethod
    def _slugify(text: str) -> str:
        """
        Convert arbitrary text into a valid kebab-case slug.

        Examples:
            "Build me a Todo App!!" → "build-me-a-todo-app"
            "My  Cool   Project"   → "my-cool-project"
            "  hello world 123  "  → "hello-world-123"
        """
        text = text.strip().lower()
        # Replace any non-alphanumeric character with a hyphen
        text = re.sub(r"[^a-z0-9]+", "-", text)
        # Remove leading/trailing hyphens
        text = text.strip("-")
        # Collapse consecutive hyphens
        text = re.sub(r"-{2,}", "-", text)
        return text

    @staticmethod
    def _resolve_status(project: ProjectInfo) -> str:
        """Check if the project's tracked PID is still alive."""
        if project.pid is not None and _is_process_alive(project.pid):
            return "running"
        return "stopped"


# ──────────────────────────────────────────────
# Process Utilities
# ──────────────────────────────────────────────

def _is_process_alive(pid: int) -> bool:
    """
    Check if a process with the given PID is still running.

    Uses signal 0 which doesn't actually send a signal,
    but checks whether the process exists and we have permission to signal it.
    """
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _kill_process(pid: int) -> None:
    """
    Attempt to gracefully terminate a process, then force-kill if needed.

    Sends SIGTERM first, waits briefly, then SIGKILL if still alive.
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return  # Already dead

    # Give it a moment to shut down gracefully
    import time
    for _ in range(10):
        if not _is_process_alive(pid):
            return
        time.sleep(0.1)

    # Force kill
    try:
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
