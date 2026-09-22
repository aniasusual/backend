"""
Agent Lifecycle Manager: Handles idle state tracking, session parking, and on-demand revival.
Replicates Oh My Pi's registry/agent-lifecycle.ts.
"""

import time
import logging
import threading
from typing import Any, Dict, List, Optional
from .registry import AgentRegistry
from .types import SubagentProgress

logger = logging.getLogger(__name__)

DEFAULT_IDLE_TTL_SECONDS = 420.0  # 7 minutes default idle TTL


class AgentLifecycleManager:
    """
    Monitors subagents, parks idle sessions past TTL to reclaim memory,
    and dynamically revives them from disk when contacted.
    """

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        idle_ttl_seconds: float = DEFAULT_IDLE_TTL_SECONDS,
    ):
        self.registry = registry or AgentRegistry.get_global()
        self.idle_ttl_seconds = idle_ttl_seconds
        self._lock = threading.RLock()
        self._idle_since: Dict[str, float] = {}

        # Automatically clear idle tracking when agents finish
        def _on_registry_change(event_type: str, progress: SubagentProgress) -> None:
            if progress.status in ("completed", "failed", "aborted"):
                with self._lock:
                    self._idle_since.pop(progress.id, None)

        self.registry.on_change(_on_registry_change)

    def mark_idle(self, agent_id: str) -> None:
        """Mark an agent as idle and start TTL countdown."""
        with self._lock:
            self._idle_since[agent_id] = time.time()
        self.registry.update_status(agent_id, "idle")

    def mark_busy(self, agent_id: str) -> None:
        """Mark an agent as busy (cancel idle countdown)."""
        with self._lock:
            self._idle_since.pop(agent_id, None)
        self.registry.update_status(agent_id, "running")

    def park(self, agent_id: str) -> bool:
        """Park an idle agent to release memory while preserving transcript files."""
        with self._lock:
            self._idle_since.pop(agent_id, None)
        success = self.registry.update_status(agent_id, "parked")
        if success:
            logger.info("Agent '%s' parked.", agent_id)
        return success

    def check_idle_parking(self, now: Optional[float] = None) -> List[str]:
        """Check all idle agents and park any that exceeded the TTL."""
        current_time = now if now is not None else time.time()
        parked_agents: List[str] = []

        with self._lock:
            items = list(self._idle_since.items())

        for agent_id, idle_timestamp in items:
            progress = self.registry.get(agent_id)
            # Only park if the agent exists and is genuinely idle
            if not progress or progress.status != "idle":
                with self._lock:
                    self._idle_since.pop(agent_id, None)
                continue

            if (current_time - idle_timestamp) >= self.idle_ttl_seconds:
                if self.park(agent_id):
                    parked_agents.append(agent_id)

        return parked_agents

    def revive(self, agent_id: str) -> Optional[Any]:
        """
        Revive a parked agent on demand (e.g. when receiving a peer hub message).
        Invokes registered reviver hook and restores session to idle.
        """
        progress = self.registry.get(agent_id)
        if not progress:
            return None

        # Only parked agents need revival
        if progress.status != "parked":
            return None

        reviver = self.registry.get_reviver(agent_id)
        revived_session = None
        if reviver:
            try:
                revived_session = reviver()
            except Exception as err:
                logger.error("Failed to revive agent '%s': %s", agent_id, err)
                return None

        self.mark_idle(agent_id)
        logger.info("Agent '%s' revived successfully.", agent_id)
        return revived_session
