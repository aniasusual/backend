"""
Agent Registry: Global tracking ledger for subagent status and lifecycle.
Replicates Oh My Pi's registry/agent-registry.ts.
"""

import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from .types import SubagentProgress, SubagentStatus

VALID_STATUSES: Set[str] = {
    "pending",
    "running",
    "idle",
    "parked",
    "completed",
    "failed",
    "aborted",
}


class AgentRegistry:
    """
    Global in-memory ledger tracking all active, idle, and parked subagents.
    Thread-safe implementation with status transition validation.
    """
    _instance: Optional["AgentRegistry"] = None
    _lock = threading.RLock()

    @classmethod
    def get_global(cls) -> "AgentRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = AgentRegistry()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for test isolation)."""
        with cls._lock:
            cls._instance = None

    def __init__(self):
        self._lock = threading.RLock()
        self._agents: Dict[str, SubagentProgress] = {}
        self._session_files: Dict[str, Path] = {}
        self._revivers: Dict[str, Callable[[], Any]] = {}
        self._listeners: List[Callable[[str, SubagentProgress], None]] = []

    def register(
        self,
        id: str,
        progress: SubagentProgress,
        session_file: Optional[Path] = None,
        reviver: Optional[Callable[[], Any]] = None,
    ) -> None:
        """Register a new subagent in the global ledger."""
        with self._lock:
            self._agents[id] = progress
            if session_file:
                self._session_files[id] = session_file
            if reviver:
                self._revivers[id] = reviver
        self._notify("registered", progress)

    def get(self, id: str) -> Optional[SubagentProgress]:
        """Retrieve subagent progress record by ID."""
        with self._lock:
            return self._agents.get(id)

    def get_session_file(self, id: str) -> Optional[Path]:
        """Retrieve the transcript file path for an agent."""
        with self._lock:
            return self._session_files.get(id)

    def get_reviver(self, id: str) -> Optional[Callable[[], Any]]:
        """Retrieve the registered session reviver hook."""
        with self._lock:
            return self._revivers.get(id)

    def update_status(self, id: str, status: SubagentStatus) -> bool:
        """Update an agent's lifecycle status and notify listeners."""
        if status not in VALID_STATUSES:
            return False
        with self._lock:
            progress = self._agents.get(id)
            if not progress:
                return False
            progress.status = status
        self._notify("status_changed", progress)
        return True

    def get_active_peers(self, exclude_id: Optional[str] = None) -> List[SubagentProgress]:
        """Return all peers currently in 'running' or 'idle' states."""
        clean_exclude = exclude_id.strip() if exclude_id else None
        with self._lock:
            return [
                p for p_id, p in self._agents.items()
                if (clean_exclude is None or p_id != clean_exclude) and p.status in ("running", "idle")
            ]

    def list_all(self, status: Optional[str] = None) -> List[SubagentProgress]:
        """List all agents, optionally filtered by status."""
        with self._lock:
            if status:
                return [p for p in self._agents.values() if p.status == status]
            return list(self._agents.values())

    def on_change(self, listener: Callable[[str, SubagentProgress], None]) -> None:
        """Register a callback for agent lifecycle changes."""
        with self._lock:
            self._listeners.append(listener)

    def _notify(self, event_type: str, progress: SubagentProgress) -> None:
        with self._lock:
            current_listeners = list(self._listeners)
        for listener in current_listeners:
            try:
                listener(event_type, progress)
            except Exception:
                pass
