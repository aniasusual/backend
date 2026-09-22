"""
The unified TaskTool implementation.
Replicates Oh My Pi's task/index.ts.

Provides the single `task` delegation tool for both single-agent and batch-agent invocations.
Enforces preflight validation, recursion depth limits, blockedAgent recursion guards,
and coordinates synchronous execution and asynchronous background job registration.
"""

import asyncio
import uuid
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .types import TaskItem, TaskParams, SingleResult
from .structured_subagent import (
    resolve_effective_subagent_policy,
    run_structured_subagent,
    StructuredSubagentError,
    can_spawn_at_depth,
)
from .discovery import get_agent

logger = logging.getLogger(__name__)


def _repair_item_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Repair individual task item fields."""
    item = dict(d)
    # Deserialize stringified output_schema
    for k in ("output_schema", "outputSchema", "output"):
        if isinstance(item.get(k), str):
            import json
            try:
                parsed = json.loads(item[k])
                if isinstance(parsed, dict):
                    item[k] = parsed
            except Exception:
                pass
    # Normalize string tools
    if isinstance(item.get("tools"), str):
        item["tools"] = [t.strip() for t in item["tools"].split(",") if t.strip()]
    # Normalize agent name
    if isinstance(item.get("agent"), str):
        item["agent"] = item["agent"].strip()
    return item


def repair_task_params(raw: Any) -> Dict[str, Any]:
    """
    Repair and normalize parameters from model invocations that may have mild formatting errors.
    """
    if not isinstance(raw, dict):
        return {"task": str(raw)}

    repaired = _repair_item_dict(raw)

    # If tasks is provided as a JSON string instead of a parsed list
    if isinstance(repaired.get("tasks"), str):
        import json
        try:
            repaired["tasks"] = json.loads(repaired["tasks"])
        except Exception:
            pass

    # Repair each item in tasks list
    if isinstance(repaired.get("tasks"), list):
        repaired["tasks"] = [
            _repair_item_dict(t) if isinstance(t, dict) else t
            for t in repaired["tasks"]
        ]

    return repaired

def validate_task_params(params: Dict[str, Any], batch_enabled: bool) -> Optional[str]:
    """
    Validate wire parameters against the single or batch contract.
    """
    has_top_task = bool(params.get("task") and str(params.get("task")).strip())
    tasks = params.get("tasks")

    if batch_enabled and tasks is not None:
        if not isinstance(tasks, list) or len(tasks) == 0:
            return "Missing `tasks`. Provide at least one task item ({ name?, agent?, task })."
        if has_top_task:
            return "Top-level `task` is not part of the batch shape. Put the work in `tasks[]` items."
        if not params.get("context") or not str(params.get("context")).strip():
            return "Missing `context`. Provide the shared background for this batch (goal, constraints, and shared contracts)."

        # Validate each item in the batch
        seen_names: Set[str] = set()
        for idx, item in enumerate(tasks):
            if not isinstance(item, dict) or not item.get("task") or not str(item.get("task")).strip():
                return f"Task {idx + 1} is missing `task` instructions."
            name = item.get("name")
            if name:
                norm_name = str(name).strip().lower()
                if norm_name in seen_names:
                    return f"Duplicate task name '{name}'. Names must be unique within a batch call."
                seen_names.add(norm_name)

        return None

    if not has_top_task:
        return "Missing `task`. Provide complete, self-contained instructions for the agent."

    return None


class TaskTool:
    """
    The unified subagent delegation tool.
    Replaces all individual invoke_*_agent tools with a single model-facing interface.
    """

    def __init__(
        self,
        tool_registry: Any,
        max_recursion_depth: int = 2,
        async_job_manager: Optional[Any] = None,
    ):
        self.tool_registry = tool_registry
        self.max_recursion_depth = max_recursion_depth
        self.async_job_manager = async_job_manager
        self.last_run_events: List[Dict[str, Any]] = []
        self.last_run_metrics: Dict[str, Any] = {}

    async def execute(
        self,
        tool_call_id: str,
        raw_params: Any,
        context: Dict[str, Any],
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task delegation tool call.
        """
        params = repair_task_params(raw_params)
        batch_enabled = "tasks" in params and params["tasks"] is not None

        self.last_run_events.clear()
        self.last_run_metrics.clear()

        def tracking_callback(evt: Dict[str, Any]) -> None:
            self.last_run_events.append(dict(evt))
            if event_callback:
                try:
                    event_callback(evt)
                except Exception:
                    pass

        # 1. Parameter validation
        val_error = validate_task_params(params, batch_enabled)
        if val_error:
            return {
                "content": [{"type": "text", "text": f"Task validation failed: {val_error}"}],
                "details": {"results": [], "error": val_error},
            }

        # 2. Resolve items to spawn
        items: List[TaskItem] = []
        if batch_enabled and isinstance(params["tasks"], list):
            for t in params["tasks"]:
                items.append(
                    TaskItem(
                        name=t.get("name"),
                        agent=t.get("agent") or "task",
                        task=t.get("task", ""),
                        output_schema=t.get("output_schema") or t.get("outputSchema"),
                        schema_mode=t.get("schema_mode") or t.get("schemaMode") or "permissive",
                        tools=t.get("tools"),
                        effort=t.get("effort"),
                        isolated=t.get("isolated"),
                    )
                )
        else:
            items.append(
                TaskItem(
                    name=params.get("name"),
                    agent=params.get("agent") or "task",
                    task=params.get("task", ""),
                    output_schema=params.get("output_schema") or params.get("outputSchema"),
                    schema_mode=params.get("schema_mode") or params.get("schemaMode") or "permissive",
                    tools=params.get("tools"),
                    effort=params.get("effort"),
                    isolated=params.get("isolated"),
                )
            )

        # 3. Preflight policy resolution for every spawn item
        project_root = Path(context.get("project_root") or getattr(self.tool_registry, "sandbox_path", "."))
        current_depth = context.get("task_depth", 0)
        blocked_agent = context.get("blocked_agent")
        parent_spawns = context.get("parent_spawns")

        policies = []
        preflight_failures = []
        for idx, item in enumerate(items):
            try:
                defn = resolve_effective_subagent_policy(
                    agent_name=item.agent,
                    project_root=project_root,
                    current_depth=current_depth,
                    max_depth=self.max_recursion_depth,
                    blocked_agent=blocked_agent,
                    parent_spawns=parent_spawns,
                )
                policies.append((item, defn))
            except StructuredSubagentError as err:
                preflight_failures.append(f"Task {item.name or f'#{idx + 1}'} failed preflight: {err.message}")

        if preflight_failures:
            error_summary = "\n".join(preflight_failures)
            return {
                "content": [{"type": "text", "text": f"Task preflight rejected:\n{error_summary}"}],
                "details": {"results": [], "error": error_summary},
            }

        # 4. Check whether to run async or sync
        # If async_job_manager is active and none of the items are marked blocking:
        results: List[SingleResult] = []
        scheduled_jobs: List[Dict[str, Any]] = []

        for idx, (item, defn) in enumerate(policies):
            agent_id = item.name or f"{item.agent}_{uuid.uuid4().hex[:6]}"
            child_context = {
                **context,
                "task_depth": current_depth + 1,
                "blocked_agent": item.agent,
                "parent_spawns": defn.spawns,
                "batch_context": params.get("context"),
            }

            # Execution mode: Subagents run inline by default so all steps stream live to the UI
            # and the parent agent receives the deliverable. Run background only if explicitly requested.
            is_async_requested = bool(params.get("async") or params.get("detached") or getattr(item, "detached", False))
            if self.async_job_manager and is_async_requested and not defn.blocking:
                job_id = self.async_job_manager.register(
                    agent_id=agent_id,
                    task_item=item,
                    agent_definition=defn,
                    context=child_context,
                    tool_registry=self.tool_registry,
                    event_callback=tracking_callback,
                    client=client,
                )
                scheduled_jobs.append({"agentId": agent_id, "jobId": job_id, "agent": item.agent})
            else:
                # Synchronous inline execution
                res = await run_structured_subagent(
                    task_item=item,
                    agent_definition=defn,
                    context=child_context,
                    tool_registry=self.tool_registry,
                    agent_id=agent_id,
                    event_callback=tracking_callback,
                    client=client,
                )
                results.append(res)

        # 5. Format response
        if scheduled_jobs and not results:
            # All items were scheduled asynchronously
            job_listings = "\n".join(f"- `{j['agentId']}` (job `{j['jobId']}`)" for j in scheduled_jobs)
            msg = (
                f"Spawned {len(scheduled_jobs)} background subagent(s):\n{job_listings}\n"
                "Results will auto-deliver upon completion. Use `hub` to inspect or coordinate."
            )
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {"scheduled": scheduled_jobs, "results": []},
            }

        # Format synchronous results
        summaries = []
        for r in results:
            status_tag = "Completed" if r.exit_code == 0 else f"Failed: {r.error}"
            summaries.append(f"### Subagent `{r.id}` ({r.agent}) — {status_tag}\n{r.output}")

        full_summary = "\n\n".join(summaries)
        total_prompt = sum(r.prompt_tokens for r in results)
        total_comp = sum(r.completion_tokens for r in results)
        total_tokens = sum(r.total_tokens for r in results)
        total_dur = sum(r.duration_ms for r in results)
        self.last_run_metrics = {
            "prompt_tokens": total_prompt,
            "completion_tokens": total_comp,
            "total_tokens": total_tokens,
            "total_duration_ms": round(total_dur, 2),
            "requests": sum(r.requests for r in results),
        }

        return {
            "content": [{"type": "text", "text": full_summary}],
            "details": {
                "results": [r.model_dump() for r in results],
                "scheduled": scheduled_jobs,
                "subagentEvents": list(self.last_run_events),
                "subagentMetrics": dict(self.last_run_metrics),
            },
        }
