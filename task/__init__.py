"""
Lowkey Task Subsystem: Replicating Oh My Pi subagent architecture.
"""

from .types import (
    AgentDefinition,
    AgentSource,
    ThinkingLevel,
    SchemaMode,
    SubagentStatus,
    LifecycleStatus,
    TaskItem,
    TaskParams,
    SingleResult,
    SubagentProgress,
    SubagentLifecyclePayload,
    HubMessage,
)
from .agents import (
    extract_frontmatter_and_body,
    parse_agent_markdown,
    load_bundled_agents,
    get_bundled_agent,
    clear_bundled_agents_cache,
)
from .discovery import (
    discover_agents,
    get_agent,
    list_agents,
)
from .yield_tool import YieldTool
from .schema_validator import validate_schema
from .prompt_renderer import (
    render_subagent_system_prompt,
    render_subagent_user_prompt,
    render_yield_reminder,
)
from .executor import run_subprocess
from .structured_subagent import (
    resolve_effective_subagent_policy,
    run_structured_subagent,
    StructuredSubagentError,
    can_spawn_at_depth,
)
from .worktree import (
    is_git_repo,
    prepare_isolation_worktree,
    capture_worktree_patch,
    apply_patch_to_root,
    cleanup_isolation_worktree,
)
from .tool import TaskTool, repair_task_params, validate_task_params
from .registry import AgentRegistry
from .lifecycle import AgentLifecycleManager
from .async_jobs import AsyncJobManager
from .hub import IrcBus, HubTool

__all__ = [
    "AgentDefinition",
    "AgentSource",
    "ThinkingLevel",
    "SchemaMode",
    "SubagentStatus",
    "LifecycleStatus",
    "TaskItem",
    "TaskParams",
    "SingleResult",
    "SubagentProgress",
    "SubagentLifecyclePayload",
    "HubMessage",
    "extract_frontmatter_and_body",
    "parse_agent_markdown",
    "load_bundled_agents",
    "get_bundled_agent",
    "clear_bundled_agents_cache",
    "discover_agents",
    "get_agent",
    "list_agents",
    "YieldTool",
    "validate_schema",
    "render_subagent_system_prompt",
    "render_subagent_user_prompt",
    "render_yield_reminder",
    "run_subprocess",
    "resolve_effective_subagent_policy",
    "run_structured_subagent",
    "StructuredSubagentError",
    "can_spawn_at_depth",
    "is_git_repo",
    "prepare_isolation_worktree",
    "capture_worktree_patch",
    "apply_patch_to_root",
    "cleanup_isolation_worktree",
    "TaskTool",
    "repair_task_params",
    "validate_task_params",
    "AgentRegistry",
    "AgentLifecycleManager",
    "AsyncJobManager",
    "IrcBus",
    "HubTool",
]
