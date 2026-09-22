"""
AsyncJobManager: Manages non-blocking concurrent subagent tasks.
Replicates Oh My Pi's async job engine and auto-delivery contract.
"""

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .types import TaskItem, AgentDefinition, SingleResult, SubagentProgress
from .structured_subagent import run_structured_subagent
from .registry import AgentRegistry

logger = logging.getLogger(__name__)


class AsyncJobManager:
    """
    Manages background execution of asynchronous subagents.
    Provides job status queries, cancellation, and auto-delivery queues.
    """
    _instance: Optional["AsyncJobManager"] = None
    _lock = threading.RLock()

    @classmethod
    def get_global(cls) -> "AsyncJobManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = AsyncJobManager()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def __init__(self, registry: Optional[AgentRegistry] = None):
        self.registry = registry or AgentRegistry.get_global()
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._pending_deliveries: List[SingleResult] = []
    def register(
        self,
        agent_id: str,
        task_item: TaskItem,
        agent_definition: AgentDefinition,
        context: Dict[str, Any],
        tool_registry: Any,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        client: Optional[Any] = None,
    ) -> str:
        """
        Schedule a non-blocking subagent task in the background.
        Returns unique job_id.
        """
        job_id = f"job_{uuid.uuid4().hex[:6]}"

        # Initialize progress tracking in registry
        progress = SubagentProgress(
            id=agent_id,
            agent=agent_definition.name,
            agent_source=agent_definition.source,
            status="running",
            task=task_item.task,
            assignment=task_item.task,
        )
        self.registry.register(agent_id, progress)

        job_record = {
            "job_id": job_id,
            "agent_id": agent_id,
            "agent": agent_definition.name,
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
        }
        self._jobs[job_id] = job_record

        async def _job_runner():
            try:
                result = await run_structured_subagent(
                    task_item=task_item,
                    agent_definition=agent_definition,
                    context=context,
                    tool_registry=tool_registry,
                    agent_id=agent_id,
                    event_callback=event_callback,
                    client=client,
                )
                job_record["status"] = "completed" if result.exit_code == 0 else "failed"
                job_record["result"] = result
                self.registry.update_status(agent_id, job_record["status"])
                with self._lock:
                    self._pending_deliveries.append(result)
            except asyncio.CancelledError:
                job_record["status"] = "aborted"
                self.registry.update_status(agent_id, "aborted")
                with self._lock:
                    if not any(d.id == agent_id and d.aborted for d in self._pending_deliveries):
                        aborted_res = SingleResult(
                            id=agent_id,
                            agent=agent_definition.name,
                            task=task_item.task,
                            assignment=task_item.task,
                            exit_code=1,
                            aborted=True,
                            abort_reason="Job cancelled",
                            error="Job cancelled by caller",
                        )
                        self._pending_deliveries.append(aborted_res)
            except Exception as err:
                job_record["status"] = "failed"
                job_record["error"] = str(err)
                self.registry.update_status(agent_id, "failed")
                failed_res = SingleResult(
                    id=agent_id,
                    agent=agent_definition.name,
                    task=task_item.task,
                    assignment=task_item.task,
                    exit_code=1,
                    error=str(err),
                )
                with self._lock:
                    self._pending_deliveries.append(failed_res)
        task = asyncio.create_task(_job_runner())
        self._tasks[job_id] = task
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve job record by ID."""
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all background jobs, optionally filtered by status."""
        if status:
            return [j for j in self._jobs.values() if j["status"] == status]
        return list(self._jobs.values())

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running background subagent task."""
        with self._lock:
            task = self._tasks.get(job_id)
            if task and not task.done():
                task.cancel()
                job_record = self._jobs.get(job_id)
                if job_record:
                    job_record["status"] = "aborted"
                    self.registry.update_status(job_record["agent_id"], "aborted")
                    # Immediately deliver aborted result
                    aborted_res = SingleResult(
                        id=job_record["agent_id"],
                        agent=job_record.get("agent", "task"),
                        task="",
                        assignment="",
                        exit_code=1,
                        aborted=True,
                        abort_reason="Job cancelled",
                        error="Job cancelled by caller",
                    )
                    self._pending_deliveries.append(aborted_res)
                return True
            return False

    def consume_deliveries(self) -> List[SingleResult]:
        """Drain and return all settled background deliverables awaiting delivery."""
        with self._lock:
            deliveries = list(self._pending_deliveries)
            self._pending_deliveries.clear()
            return deliveries
