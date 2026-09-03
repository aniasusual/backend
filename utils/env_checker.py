"""
Environment checker for Lowkey.

Verifies system dependencies (Node.js, npm, Python) to provide
clear, actionable diagnostic messages to the user if tools are missing.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Dict, Any, Optional


def get_command_version(command: str) -> Optional[str]:
    """Execute command with --version and return the output string, or None if unavailable."""
    if not shutil.which(command):
        return None
    try:
        res = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return None


def check_node_environment() -> Dict[str, Any]:
    """
    Check if Node.js and npm are available in the system path.

    Returns:
        Dict with keys:
            - available: bool (True if both node and npm exist)
            - node_version: str | None
            - npm_version: str | None
            - error: str | None (Actionable error message if missing)
    """
    node_ver = get_command_version("node")
    npm_ver = get_command_version("npm")

    if not node_ver and not npm_ver:
        return {
            "available": False,
            "node_version": None,
            "npm_version": None,
            "error": (
                "Node.js and npm were not found in your system PATH. "
                "Please install Node.js (v18 or higher) from https://nodejs.org "
                "to run React and Node.js projects."
            ),
        }

    if not node_ver:
        return {
            "available": False,
            "node_version": None,
            "npm_version": npm_ver,
            "error": "Node.js executable was not found. Please install Node.js from https://nodejs.org.",
        }

    if not npm_ver:
        return {
            "available": False,
            "node_version": node_ver,
            "npm_version": None,
            "error": "npm executable was not found. Please ensure npm is installed alongside Node.js.",
        }

    return {
        "available": True,
        "node_version": node_ver,
        "npm_version": npm_ver,
        "error": None,
    }
