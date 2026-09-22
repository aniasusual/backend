"""
Data structures, schemas, and event types for the Lowkey task subagent subsystem.
Directly replicates the contracts from Oh My Pi (packages/coding-agent/src/task/types.ts).
"""

from typing import Dict, Any, List, Optional, Literal, Union
from pydantic import BaseModel, ConfigDict, Field, AliasChoices

AgentSource = Literal["bundled", "user", "project"]
ThinkingLevel = Literal["lo", "med", "hi", "auto"]
SchemaMode = Literal["permissive", "strict"]
SubagentStatus = Literal["pending", "running", "idle", "parked", "completed", "failed", "aborted"]
LifecycleStatus = Literal["started", "idle", "parked", "revived", "completed", "failed", "aborted"]


class AgentDefinition(BaseModel):
    """
    Metadata, tool permissions, execution characteristics, and system prompt
    for an individual agent role.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str
    description: str = ""
    tools: List[str] = Field(default_factory=list)
    model: Optional[str] = None  # e.g. "@smol", "@slow", "@task", or explicit model ID
    thinking_level: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("thinking_level", "thinkingLevel", "thinking-level"),
    )
    spawns: Optional[str] = None  # "*", specific agent names comma-separated, or None
    blocking: bool = False
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("output_schema", "outputSchema", "output"),
    )
    read_summarize: bool = Field(
        default=True,
        validation_alias=AliasChoices("read_summarize", "readSummarize", "read-summarize"),
    )
    system_prompt: str = Field(
        default="",
        validation_alias=AliasChoices("system_prompt", "systemPrompt"),
    )
    source: AgentSource = "bundled"
    file_path: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("file_path", "filePath"),
    )


class TaskItem(BaseModel):
    """
    A single subagent task item within a batch or single spawn invocation.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: Optional[str] = None
    agent: str = "task"
    task: str
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("output_schema", "outputSchema", "output"),
    )
    schema_mode: SchemaMode = Field(
        default="permissive",
        validation_alias=AliasChoices("schema_mode", "schemaMode"),
    )
    tools: Optional[List[str]] = None
    effort: Optional[Literal["lo", "med", "hi"]] = None
    isolated: Optional[bool] = None


class TaskParams(BaseModel):
    """
    Wire parameters accepted by the `task` tool.
    Supports flat/single spawn mode as well as batch `{ context, tasks: [...] }` mode.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # Flat / Single-agent spawn fields
    name: Optional[str] = None
    agent: Optional[str] = None
    task: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("output_schema", "outputSchema", "output"),
    )
    schema_mode: Optional[SchemaMode] = Field(
        default=None,
        validation_alias=AliasChoices("schema_mode", "schemaMode"),
    )
    tools: Optional[List[str]] = None
    effort: Optional[Literal["lo", "med", "hi"]] = None
    isolated: Optional[bool] = None

    # Batch spawn fields
    context: Optional[str] = None
    tasks: Optional[List[TaskItem]] = None

class SingleResult(BaseModel):
    """
    The settled result of a single subagent execution.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    index: int = 0
    id: str
    agent: str
    agent_source: str = "bundled"
    task: str
    assignment: str
    description: Optional[str] = None
    exit_code: int = 0
    output: str = ""
    stderr: Optional[str] = None
    structured_output: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0
    model_override: Optional[str] = None
    model_role: Optional[str] = None
    error: Optional[str] = None
    aborted: bool = False
    abort_reason: Optional[str] = None
    worktree_path: Optional[str] = None
    patch: Optional[str] = None


class SubagentProgress(BaseModel):
    """
    Real-time progress telemetry snapshot for an active or historical subagent.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    index: int = 0
    agent: str
    agent_source: str = "bundled"
    model_role: Optional[str] = None
    status: SubagentStatus = "pending"
    task: str
    assignment: str
    recent_tools: List[str] = Field(default_factory=list)
    recent_output: List[str] = Field(default_factory=list)
    tool_count: int = 0
    requests: int = 0
    tokens: int = 0
    cost: float = 0.0
    duration_ms: float = 0.0
    context_tokens: Optional[int] = None
    context_window: Optional[int] = None
    extracted_tool_data: Optional[Dict[str, Any]] = None


class SubagentLifecyclePayload(BaseModel):
    """
    Payload emitted when a subagent lifecycle event occurs.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    agent: str
    agent_source: str = "bundled"
    status: LifecycleStatus
    session_file: Optional[str] = None
    index: int = 0
    parent_tool_call_id: Optional[str] = None
    detached: bool = False
    error: Optional[str] = None


class HubMessage(BaseModel):
    """
    Peer-to-peer coordination message between agents.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: str
    from_agent: str
    to_agent: str  # recipient agent id or "all"
    message: str
    reply_to: Optional[str] = None
    timestamp: str
