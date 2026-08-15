"""
Data models for the Lowkey Project Manager.

Defines ProjectInfo — the canonical representation of a user project,
along with serialization helpers for reading/writing project metadata.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Metadata filename stored inside each project directory.
META_FILENAME = ".lowkey_meta.json"


@dataclass
class ProjectInfo:
    """
    Represents a single Lowkey project with its filesystem location,
    runtime state, and metadata.

    Persisted fields (saved to .lowkey_meta.json):
        name, created_at, last_opened

    Runtime fields (derived at query time, not persisted):
        path, status, port, pid
    """

    name: str
    path: Path
    status: str = "stopped"         # "running" | "stopped"
    port: Optional[int] = None
    pid: Optional[int] = None
    created_at: str = field(default_factory=lambda: _now_iso())
    last_opened: str = field(default_factory=lambda: _now_iso())

    def to_dict(self) -> dict:
        """Serialize to a plain dict (for WebSocket JSON responses)."""
        return {
            "name": self.name,
            "path": str(self.path),
            "status": self.status,
            "port": self.port,
            "pid": self.pid,
            "created_at": self.created_at,
            "last_opened": self.last_opened,
        }

    def save_meta(self) -> None:
        """Persist the metadata fields to .lowkey_meta.json inside the project directory."""
        meta_path = self.path / META_FILENAME
        meta = {
            "name": self.name,
            "created_at": self.created_at,
            "last_opened": self.last_opened,
            "pid": self.pid,
            "port": self.port,
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    @classmethod
    def from_directory(cls, project_dir: Path) -> Optional[ProjectInfo]:
        """
        Reconstruct a ProjectInfo from an existing project directory
        by reading its .lowkey_meta.json file.

        Returns None if the directory doesn't contain valid metadata.
        """
        meta_path = project_dir / META_FILENAME
        if not meta_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        return cls(
            name=meta.get("name", project_dir.name),
            path=project_dir,
            created_at=meta.get("created_at", ""),
            last_opened=meta.get("last_opened", ""),
            pid=meta.get("pid"),
            port=meta.get("port"),
            # status is resolved later by checking if PID is alive
            status="stopped",
        )


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
