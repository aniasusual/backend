"""
Structured Subagent Policy Resolution and Execution.
Replicates Oh My Pi's task/structured-subagent.ts.

Coordinates preflight validation, recursion depth checks, blockedAgent prevention,
worktree isolation preparation, execution dispatch, and patch merge.
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .types import AgentDefinition, SingleResult, TaskItem
from .discovery import get_agent, discover_agents
from .executor import run_subprocess
from .worktree import (
    prepare_isolation_worktree,
    capture_worktree_patch,
    apply_patch_to_root,
    cleanup_isolation_worktree,
    WorktreeToolRegistryProxy,
)
class StructuredSubagentError(Exception):
    """Raised when subagent preflight, recursion, or isolation checks fail."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def can_spawn_at_depth(max_depth: int, current_depth: int) -> bool:
    """Check if task depth has reached the configured maximum recursion ceiling."""
    if max_depth < 0:
        return True
    return current_depth < max_depth


def resolve_effective_subagent_policy(
    agent_name: str,
    project_root: Optional[Path],
    current_depth: int = 0,
    max_depth: int = 2,
    blocked_agent: Optional[str] = None,
    parent_spawns: Optional[str] = None,
) -> AgentDefinition:
    """
    Perform preflight validation:
    1. Verify recursion depth limit has not been exceeded.
    2. Enforce recursion guard: an agent cannot spawn itself (blockedAgent).
    3. Verify parent spawns whitelist permission.
    4. Resolve and return the AgentDefinition from project, user, or bundled sources.
    """
    # 1. Depth check
    if not can_spawn_at_depth(max_depth, current_depth):
        raise StructuredSubagentError(
            "preflight",
            f"Cannot spawn another agent at task depth {current_depth}; maximum depth is {max_depth}."
        )

    # 2. Blocked agent self-spawn guard (case-insensitive)
    if blocked_agent and blocked_agent.strip().lower() == agent_name.strip().lower():
        raise StructuredSubagentError(
            "preflight",
            f"Cannot spawn {blocked_agent} agent from within itself (recursion prevention). Use a different agent type."
        )

    # 3. Spawns permission check
    if current_depth > 0:
        if not parent_spawns:
            raise StructuredSubagentError(
                "preflight",
                f"Subagent at depth {current_depth} does not have permission to spawn '{agent_name}'. No spawns permitted."
            )
        if parent_spawns != "*":
            allowed = [s.strip().lower() for s in parent_spawns.split(",") if s.strip()]
            if agent_name.strip().lower() not in allowed:
                raise StructuredSubagentError(
                    "preflight",
                    f"Parent agent does not have permission to spawn '{agent_name}'. Allowed: {allowed}"
                )
    elif parent_spawns is not None and parent_spawns != "":
        if parent_spawns != "*":
            allowed = [s.strip().lower() for s in parent_spawns.split(",") if s.strip()]
            if agent_name.strip().lower() not in allowed:
                raise StructuredSubagentError(
                    "preflight",
                    f"Parent agent does not have permission to spawn '{agent_name}'. Allowed: {allowed}"
                )
    # 4. Resolve agent definition
    agent_defn = get_agent(agent_name, project_root=project_root)
    if not agent_defn:
        all_discovered = discover_agents(project_root=project_root)
        avail = ", ".join(sorted(all_discovered.keys())) or "none"
        raise StructuredSubagentError(
            "preflight",
            f"Unknown agent '{agent_name}'. Available: {avail}"
        )

    return agent_defn


async def run_structured_subagent(
    task_item: TaskItem,
    agent_definition: AgentDefinition,
    context: Dict[str, Any],
    tool_registry: Any,
    agent_id: str,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    client: Optional[Any] = None,
) -> SingleResult:
    """
    Execute a structured subagent request with full isolation and error handling.
    """
    project_root = Path(context.get("project_root") or getattr(tool_registry, "sandbox_path", "."))
    isolated = bool(task_item.isolated)

    worktree_path: Optional[Path] = None
    branch_name: Optional[str] = None
    isolation_err: Optional[str] = None

    # 1. Prepare Git worktree isolation if requested
    if isolated:
        worktree_path, branch_name, isolation_err = prepare_isolation_worktree(project_root, agent_id)
        if isolation_err:
            return SingleResult(
                id=agent_id,
                agent=agent_definition.name,
                agent_source=agent_definition.source,
                task=task_item.task,
                assignment=task_item.task,
                exit_code=1,
                error=f"Worktree isolation failed: {isolation_err}",
            )

    # 2. Execute subprocess in-process
    try:
        effective_schema = task_item.output_schema or agent_definition.output_schema
        effective_registry = (
            WorktreeToolRegistryProxy(tool_registry, worktree_path)
            if (isolated and worktree_path)
            else tool_registry
        )
        result = await run_subprocess(
            id=agent_id,
            agent_definition=agent_definition,
            assignment=task_item.task,
            tool_registry=effective_registry,
            context=context.get("batch_context"),
            plan_reference=context.get("plan_reference"),
            plan_reference_path=context.get("plan_reference_path"),
            worktree_path=str(worktree_path) if worktree_path else None,
            output_schema=effective_schema,
            schema_mode=task_item.schema_mode,
            model_name=context.get("model"),
            event_callback=event_callback,
            hub_tool=context.get("hub_tool"),
            peers=context.get("peers"),
            client=client,
        )

        # 3. If isolated, capture patch and merge if successful
        if isolated and worktree_path:
            patch_content, patch_err = capture_worktree_patch(worktree_path)
            result.patch = patch_content

            if result.exit_code == 0 and patch_content:
                applied, apply_err = apply_patch_to_root(project_root, patch_content)
                if not applied:
                    result.exit_code = 1
                    result.error = f"Changes captured in worktree, but patch failed to apply to root: {apply_err}"

        return result

    finally:
        # 4. Clean up temporary worktree
        if isolated and worktree_path:
            cleanup_isolation_worktree(project_root, worktree_path, branch_name)
