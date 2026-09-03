"""
Template Manager for Lowkey Projects.

Handles pre-scaffolding of project directories from built-in templates
and manages a shared node_modules cache for instant, zero-install bootstrap.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from utils.env_checker import check_node_environment

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

try:
    from config.settings import TEMPLATE_CACHE_DIR
except ImportError:
    TEMPLATE_CACHE_DIR = Path(os.getenv("TEMPLATE_CACHE_DIR", str(Path.home() / ".lowkey" / "template_cache"))).expanduser().resolve()


class TemplateManager:
    """
    Manages project templates and fast scaffolding.
    """

    def __init__(self, templates_dir: Optional[Path] = None, cache_dir: Optional[Path] = None):
        self.templates_dir = (templates_dir or TEMPLATES_DIR).resolve()
        self.cache_dir = (cache_dir or TEMPLATE_CACHE_DIR).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_template_path(self, template_name: str) -> Path:
        """Get the directory path for a template."""
        template_path = self.templates_dir / template_name
        if not template_path.exists() or not template_path.is_dir():
            raise ValueError(f"Template '{template_name}' not found at {template_path}")
        return template_path

    def ensure_template_dependencies(self, template_name: str = "node_react") -> Path:
        """
        Ensures dependencies for the template are installed in the global template cache.
        Runs `npm install` once if the cached node_modules does not exist.
        """
        template_src = self.get_template_path(template_name)
        cached_tpl_dir = self.cache_dir / template_name
        cached_tpl_dir.mkdir(parents=True, exist_ok=True)

        cached_node_modules = cached_tpl_dir / "node_modules"
        cached_package_json = cached_tpl_dir / "package.json"
        src_package_json = template_src / "package.json"

        # Check environment first
        env_status = check_node_environment()
        if not env_status["available"]:
            raise RuntimeError(env_status["error"])

        # Check if node_modules already exists and package.json is up-to-date
        needs_install = False
        if not cached_node_modules.exists():
            needs_install = True
        elif src_package_json.exists():
            if not cached_package_json.exists() or cached_package_json.read_text() != src_package_json.read_text():
                needs_install = True

        if needs_install:
            # Copy package.json to cache dir
            shutil.copy2(src_package_json, cached_package_json)
            
            # Run npm install in cache directory
            result = subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund"],
                cwd=str(cached_tpl_dir),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to install template dependencies in {cached_tpl_dir}:\n{result.stderr}"
                )

        return cached_node_modules

    def scaffold_project(self, project_path: Path, template_name: str = "node_react") -> None:
        """
        Scaffolds a new project directory by copying template files
        and linking cached node_modules for instant readiness.
        """
        template_src = self.get_template_path(template_name)
        project_path.mkdir(parents=True, exist_ok=True)

        # 1. Copy all template files (skipping node_modules or .git)
        for item in template_src.rglob("*"):
            if "node_modules" in item.parts or ".git" in item.parts:
                continue
            rel_path = item.relative_to(template_src)
            target_path = project_path / rel_path

            if item.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            elif item.is_file():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target_path)

        # 2. Link node_modules from cache for instant zero-wait startup
        try:
            cached_node_modules = self.ensure_template_dependencies(template_name)
            target_node_modules = project_path / "node_modules"

            if not target_node_modules.exists() and not target_node_modules.is_symlink():
                try:
                    os.symlink(cached_node_modules, target_node_modules, target_is_directory=True)
                except OSError:
                    # Fallback to copy if symlinks are not permitted on the filesystem
                    shutil.copytree(cached_node_modules, target_node_modules)
        except Exception as e:
            # If dependency pre-caching fails (e.g. offline on first run), the project files
            # are still written so the agent or user can run npm install later.
            print(f"[TemplateManager] Warning: Could not link node_modules: {e}")
