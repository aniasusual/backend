"""
Peer-to-peer Agent Hub and IRC Message Bus.
Replicates Oh My Pi's tools/hub and irc/bus.ts.

Enables concurrent subagents to discover, message, and coordinate with each other
directly without routing every message back through the parent agent.
"""

import asyncio
import logging
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .types import HubMessage
from .registry import AgentRegistry
from .lifecycle import AgentLifecycleManager
from .async_jobs import AsyncJobManager

logger = logging.getLogger(__name__)


class IrcBus:
    """
    In-memory message broker for peer-to-peer agent messaging.
    Thread-safe implementation with filtered waiters and deduplicated inboxes.
    """
    _instance: Optional["IrcBus"] = None
    _lock = threading.RLock()

    @classmethod
    def get_global(cls) -> "IrcBus":
        with cls._lock:
            if cls._instance is None:
                cls._instance = IrcBus()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def __init__(self):
        self._lock = threading.RLock()
        # Queues keyed by recipient agent id
        self._inboxes: Dict[str, List[HubMessage]] = defaultdict(list)
        # Waiters store (future, optional_from_filter)
        self._waiters: Dict[str, List[Tuple[asyncio.Future, Optional[str]]]] = defaultdict(list)

    def send(
        self,
        from_agent: str,
        to_agent: str,
        message: str,
        reply_to: Optional[str] = None,
    ) -> HubMessage:
        """Post a message to a recipient agent or broadcast to all."""
        msg = HubMessage(
            id=f"msg_{uuid.uuid4().hex[:6]}",
            from_agent=from_agent,
            to_agent=to_agent,
            message=message,
            reply_to=reply_to,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        registry = AgentRegistry.get_global()

        # If broadcast
        if to_agent == "all":
            all_agents = registry.list_all()
            for agent in all_agents:
                if agent.id != from_agent:
                    self._deliver_to_queue(agent.id, msg)
            return msg

        # Targeted send
        self._deliver_to_queue(to_agent, msg)
        return msg

    def _deliver_to_queue(self, recipient_id: str, msg: HubMessage) -> None:
        with self._lock:
            waiters = self._waiters.get(recipient_id, [])
            delivered_to_waiter = False
            for fut, from_filter in list(waiters):
                if not fut.done() and (from_filter is None or from_filter == msg.from_agent):
                    fut.set_result(msg)
                    waiters.remove((fut, from_filter))
                    delivered_to_waiter = True
                    break  # Message consumed directly by waiter; do not duplicate into inbox
            if not delivered_to_waiter:
                self._inboxes[recipient_id].append(msg)

    def inbox(self, for_agent: str, peek: bool = False) -> List[HubMessage]:
        """Read pending messages for an agent."""
        with self._lock:
            messages = list(self._inboxes.get(for_agent, []))
            if not peek and for_agent in self._inboxes:
                self._inboxes[for_agent].clear()
            return messages

    async def wait_for_message(
        self,
        for_agent: str,
        from_agent: Optional[str] = None,
        timeout: float = 5.0,
    ) -> Optional[HubMessage]:
        """Wait for an incoming message with optional sender filter and timeout."""
        # Check if already present in inbox
        with self._lock:
            pending = self._inboxes.get(for_agent, [])
            if pending:
                if from_agent:
                    for idx, m in enumerate(pending):
                        if m.from_agent == from_agent:
                            return pending.pop(idx)
                else:
                    return pending.pop(0)

            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._waiters[for_agent].append((fut, from_agent))

        try:
            msg = await asyncio.wait_for(fut, timeout=timeout)
            return msg
        except (asyncio.TimeoutError, asyncio.CancelledError):
            with self._lock:
                if for_agent in self._waiters:
                    self._waiters[for_agent] = [
                        (f, fa) for f, fa in self._waiters[for_agent] if f is not fut
                    ]
            return None
class HubTool:
    """
    Tool implementation providing the `hub` operations for agent coordination.
    """

    def __init__(
        self,
        self_agent_id: str,
        bus: Optional[IrcBus] = None,
        registry: Optional[AgentRegistry] = None,
        lifecycle_manager: Optional[AgentLifecycleManager] = None,
        async_job_manager: Optional[AsyncJobManager] = None,
    ):
        self.self_agent_id = self_agent_id
        self.bus = bus or IrcBus.get_global()
        self.registry = registry or AgentRegistry.get_global()
        self.lifecycle_manager = lifecycle_manager
        self.async_job_manager = async_job_manager

    async def execute(
        self,
        op: str,
        to: Optional[str] = None,
        message: Optional[str] = None,
        from_agent: Optional[str] = None,
        ids: Optional[Any] = None,
        status: Optional[str] = None,
        reply_to: Optional[str] = None,
        peek: bool = False,
        timeout: float = 5.0,
        **kwargs: Any,
    ) -> str:
        """
        Execute a hub coordination operation.
        """
        op = op.lower().strip() if op else ""
        # Support 'from' alias for from_agent ('from' is a Python keyword)
        effective_from = from_agent or kwargs.get("from")

        # 1. Send peer message
        if op == "send":
            if not to:
                return "Error: `to` recipient agent ID is required for hub send."
            if not message:
                return "Error: `message` content is required for hub send."

            # If recipient is parked, revive it
            if self.lifecycle_manager and to != "all":
                recipient = self.registry.get(to)
                if recipient and recipient.status == "parked":
                    self.lifecycle_manager.revive(to)

            msg = self.bus.send(
                from_agent=self.self_agent_id,
                to_agent=to,
                message=message,
                reply_to=reply_to,
            )
            return f"Message delivered to '{to}' (id: {msg.id})."

        # 2. Check inbox
        if op == "inbox":
            messages = self.bus.inbox(for_agent=self.self_agent_id, peek=peek)
            if not messages:
                return "Inbox is empty."
            lines = [f"- [{m.from_agent} -> {m.to_agent}] ({m.timestamp}): {m.message}" for m in messages]
            return "Inbox messages:\n" + "\n".join(lines)

        # 3. Wait for peer message or job
        if op == "wait":
            msg = await self.bus.wait_for_message(
                for_agent=self.self_agent_id,
                from_agent=effective_from,
                timeout=timeout,
            )
            if msg:
                return f"Received message from '{msg.from_agent}': {msg.message}"
            return "Wait timed out. No incoming messages."

        # 4. List peer roster
        if op == "list":
            if status:
                peers = [p for p in self.registry.list_all(status=status) if p.id != self.self_agent_id]
            else:
                peers = self.registry.get_active_peers(exclude_id=self.self_agent_id)

            if not peers:
                return f"No subagents found with status '{status}'." if status else "No other active subagents currently running."
            lines = [f"- `{p.id}` — {p.agent} (status: {p.status})" for p in peers]
            header = f"Subagents (status: {status}):" if status else "Active peer agents:"
            return f"{header}\n" + "\n".join(lines)

        # 5. Snapshot background jobs
        if op == "jobs":
            if not self.async_job_manager:
                return "Async job manager is not configured."
            jobs = self.async_job_manager.list_jobs(status=status)
            if not jobs:
                return "No background jobs found."
            lines = [f"- Job `{j['job_id']}` (Agent: `{j['agent_id']}`): {j['status']}" for j in jobs]
            return "Background jobs snapshot:\n" + "\n".join(lines)

        # 6. Cancel background jobs
        if op == "cancel":
            raw_ids = ids or kwargs.get("id")
            if not self.async_job_manager or not raw_ids:
                return "Error: `ids` array of job IDs is required for hub cancel."
            if isinstance(raw_ids, str):
                job_ids = [j.strip() for j in raw_ids.split(",") if j.strip()]
            elif isinstance(raw_ids, list):
                job_ids = [str(j).strip() for j in raw_ids if str(j).strip()]
            else:
                job_ids = []

            cancelled = []
            for j_id in job_ids:
                if self.async_job_manager.cancel_job(j_id):
                    cancelled.append(j_id)
            return f"Cancelled {len(cancelled)} job(s): {', '.join(cancelled) if cancelled else 'none found'}."

        return f"Unknown hub operation '{op}'. Supported: send, inbox, wait, list, jobs, cancel."
