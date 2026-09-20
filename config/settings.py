"""
Centralized Configuration and Environment Settings for Lowkey Backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

# Locate the root backend directory and load .env
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_PATH)
except ImportError:
    pass


def _expand_path(raw_path: str) -> Path:
    """Expands tilde (~) and relative path variables."""
    return Path(os.path.expanduser(raw_path)).resolve()


# Server Network Settings
BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))

# Ollama LLM Connection
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL_ID: str = os.getenv("DEFAULT_MODEL_ID", "qwen2.5-coder:14b")

# Storage & Cache Directories
PROJECTS_ROOT: Path = _expand_path(os.getenv("PROJECTS_ROOT", str(Path.home() / ".lowkey" / "projects")))
TEMPLATE_CACHE_DIR: Path = _expand_path(os.getenv("TEMPLATE_CACHE_DIR", str(Path.home() / ".lowkey" / "template_cache")))

# CORS
raw_cors = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS: List[str] = [origin.strip() for origin in raw_cors.split(",") if origin.strip()]
if "*" in CORS_ORIGINS:
    CORS_ORIGINS = ["*"]
