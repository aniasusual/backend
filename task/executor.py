"""
Subagent Executor & Execution Engine.
Replicates Oh My Pi's task/executor.ts.

Responsibilities:
1. Tool scoping: Filters global tool registry strictly to the agent's whitelisted tools + yield + hub.
2. Prompt assembly: Uses Jinja2 templates for system prompt, user assignment, and yield reminders.
3. Drive to Yield: Executes the agent loop and automatically triggers a reminder ladder if the agent stops without calling yield.
4. Budget enforcement: Enforces soft request budgets to prevent runaway loops.
5. Structured telemetry: Emits real-time progress and lifecycle events to callbacks.
"""

import asyncio
import inspect
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import ollama

from config.settings import OLLAMA_HOST, DEFAULT_MODEL_ID
from plugins.argument_normalizer import ToolArgumentNormalizer
from tools.parser import ToolCallParser
from tools.schemas import TOOL_SCHEMAS

from .types import AgentDefinition, SingleResult, SubagentProgress
from .prompt_renderer import (
    render_subagent_system_prompt,
    render_subagent_user_prompt,
    render_yield_reminder,
)
from .yield_tool import YieldTool

logger = logging.getLogger(__name__)

# Default soft request budget (number of LLM chat requests before forced wrap-up)
DEFAULT_SOFT_REQUEST_BUDGET = 30
MAX_YIELD_RETRIES = 3

# Standard model role mappings
ROLE_MODEL_MAPPINGS: Dict[str, str] = {
    "@smol": os.getenv("SMOL_MODEL_ID", "qwen2.5-coder:7b"),
    "@slow": os.getenv("SLOW_MODEL_ID", "qwen2.5-coder:14b"),
    "@task": os.getenv("TASK_MODEL_ID", DEFAULT_MODEL_ID),
}
class SubagentRunMonitor:
    """Tracks token counts, durations, tool calls, and yield state during execution."""

    def __init__(self, id: str, agent_name: str, assignment: str):
        self.id = id
        self.agent_name = agent_name
        self.assignment = assignment
        self.start_time = time.time()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.requests = 0
        self.tool_calls_count = 0
        self.recent_tools: List[str] = []
        self.recent_output: List[str] = []
        self.yield_called = False
        self.aborted = False
        self.abort_reason: Optional[str] = None
        self.budget_stop_requested = False

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def duration_ms(self) -> float:
        return round((time.time() - self.start_time) * 1000.0, 2)

    def record_chat_metrics(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.requests += 1

    def record_tool_call(self, tool_name: str, result_summary: str) -> None:
        self.tool_calls_count += 1
        self.recent_tools.append(tool_name)
        if len(self.recent_tools) > 10:
            self.recent_tools.pop(0)

        if result_summary:
            short_res = result_summary[:120].strip()
            self.recent_output.append(f"[{tool_name}] {short_res}")
            if len(self.recent_output) > 10:
                self.recent_output.pop(0)


def build_scoped_tools(
    agent_definition: AgentDefinition,
    tool_registry: Any,
    yield_tool: YieldTool,
    hub_tool: Optional[Any] = None,
) -> Tuple[Dict[str, Callable], List[Dict[str, Any]]]:
    """
    Scope tools strictly to the agent's whitelist, plus mandatory yield and optional hub.
    Strips parent-owned bookkeeping tools (e.g. todo).
    """
    all_tools: Dict[str, Callable] = tool_registry.get_tools() if tool_registry else {}
    allowed_names: Set[str] = set(agent_definition.tools) if agent_definition.tools else set(all_tools.keys())

    # Parent-owned tools that subagents must not have
    parent_owned_tools = {"todo", "task"}
    effective_allowed = {t for t in allowed_names if t not in parent_owned_tools}

    # Always ensure yield tool is present
    effective_allowed.add("yield")
    if hub_tool is not None:
        effective_allowed.add("hub")

    # Filter tool map
    scoped_map: Dict[str, Callable] = {}
    for name, fn in all_tools.items():
        if name in effective_allowed:
            scoped_map[name] = fn

    scoped_map["yield"] = yield_tool.execute
    if hub_tool is not None and "hub" in effective_allowed:
        scoped_map["hub"] = hub_tool.execute

    # Filter schemas
    all_schemas = list(TOOL_SCHEMAS.values()) if isinstance(TOOL_SCHEMAS, dict) else TOOL_SCHEMAS
    scoped_schemas: List[Dict[str, Any]] = []
    for s in all_schemas:
        if isinstance(s, dict):
            fn_name = s.get("function", {}).get("name")
            if fn_name in effective_allowed and fn_name != "yield":
                scoped_schemas.append(s)

    # Add yield tool schema with embedded output schema
    scoped_schemas.append(yield_tool.get_schema())

    return scoped_map, scoped_schemas


async def run_subprocess(
    id: str,
    agent_definition: AgentDefinition,
    assignment: str,
    tool_registry: Any,
    context: Optional[str] = None,
    plan_reference: Optional[str] = None,
    plan_reference_path: Optional[str] = None,
    worktree_path: Optional[str] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    schema_mode: str = "permissive",
    model_name: Optional[str] = None,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    hub_tool: Optional[Any] = None,
    peers: Optional[List[Dict[str, Any]]] = None,
    soft_request_budget: int = DEFAULT_SOFT_REQUEST_BUDGET,
    max_yield_retries: int = MAX_YIELD_RETRIES,
    client: Optional[Any] = None,
) -> SingleResult:
    """
    Execute a single subagent in-process and drive it to completion via yield.
    """
    monitor = SubagentRunMonitor(id=id, agent_name=agent_definition.name, assignment=assignment)
    effective_schema = output_schema or agent_definition.output_schema
    yield_tool = YieldTool(output_schema=effective_schema, schema_mode=schema_mode)

    scoped_tools, scoped_schemas = build_scoped_tools(
        agent_definition=agent_definition,
        tool_registry=tool_registry,
        yield_tool=yield_tool,
        hub_tool=hub_tool,
    )

    # 1. Assemble system prompt
    system_prompt = render_subagent_system_prompt(
        agent_definition=agent_definition,
        context=context,
        plan_reference=plan_reference,
        plan_reference_path=plan_reference_path,
        worktree=worktree_path,
        self_id=id,
        peers=peers,
        output_schema=effective_schema,
    )

    # 2. Assemble user prompt
    user_prompt = render_subagent_user_prompt(assignment=assignment)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    agent_model = agent_definition.model
    if agent_model and (not model_name or model_name == DEFAULT_MODEL_ID):
        resolved_model = ROLE_MODEL_MAPPINGS.get(
            agent_model,
            agent_model if not agent_model.startswith("@") else DEFAULT_MODEL_ID,
        )
    elif model_name:
        resolved_model = ROLE_MODEL_MAPPINGS.get(
            model_name,
            model_name if not model_name.startswith("@") else DEFAULT_MODEL_ID,
        )
    else:
        resolved_model = DEFAULT_MODEL_ID

    def emit_event(event_type: str, data: Dict[str, Any]) -> None:
        payload = {
            "type": "subagent_event",
            "subagent": agent_definition.name,
            "id": id,
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        if event_callback:
            try:
                event_callback(payload)
            except Exception as cb_err:
                logger.warning(f"[{id}] Event callback failed: {cb_err}")

    emit_event("start", {
        "task": assignment,
        "model": resolved_model,
        "agent": agent_definition.name,
    })

    ollama_client = client or ollama.Client(host=OLLAMA_HOST)

    # 3. Main execution loop with drive to yield and hard ceiling
    last_assistant_content = ""
    retry_count = 0
    hard_request_ceiling = soft_request_budget + max_yield_retries + 2

    while True:
        # Enforce hard request ceiling to prevent infinite tool-calling loops
        if monitor.requests >= hard_request_ceiling:
            logger.warning("[%s] Hard request ceiling reached (%d requests); halting subagent execution", id, monitor.requests)
            yield_tool.called = True
            summary_text = f"Subagent halted: reached hard request ceiling ({hard_request_ceiling}). {last_assistant_content}".strip()
            yield_tool.data = {"summary": summary_text}
            break

        # Check soft request budget
        if monitor.requests >= soft_request_budget and not monitor.budget_stop_requested:
            monitor.budget_stop_requested = True
            retry_count = max_yield_retries - 1
            reminder = render_yield_reminder(retry_count=retry_count, max_retries=max_yield_retries, budget_stop=True)
            messages.append({"role": "user", "content": reminder})

        emit_event("iteration_start", {
            "requests": monitor.requests,
            "duration_ms": monitor.duration_ms,
        })

        try:
            response = await asyncio.to_thread(
                ollama_client.chat,
                model=resolved_model,
                messages=messages,
                tools=scoped_schemas if scoped_schemas else None,
                options={"temperature": 0.5, "num_ctx": 16384},
            )
        except Exception as e:
            err_msg = f"Subagent model error: {str(e)}"
            logger.error(f"[{id}] Model execution failed: {err_msg}")
            emit_event("finish", {"status": "failed", "error": err_msg})
            return SingleResult(
                id=id,
                agent=agent_definition.name,
                agent_source=agent_definition.source,
                task=user_prompt,
                assignment=assignment,
                exit_code=1,
                output="",
                error=err_msg,
                duration_ms=monitor.duration_ms,
                prompt_tokens=monitor.prompt_tokens,
                completion_tokens=monitor.completion_tokens,
                total_tokens=monitor.total_tokens,
                requests=monitor.requests,
                model_role=agent_definition.model,
                model_override=resolved_model,
                worktree_path=worktree_path,
            )

        p_tokens = response.get("prompt_eval_count") or 0
        c_tokens = response.get("eval_count") or 0
        monitor.record_chat_metrics(p_tokens, c_tokens)

        assistant_msg = response.get("message", {})
        raw_content = assistant_msg.get("content", "") or ""
        native_thinking = assistant_msg.get("thinking", "") or ""
        raw_tool_calls = assistant_msg.get("tool_calls", [])

        # Parse thinking tags (handling both closed and unclosed tags)
        think_match = re.search(r"<think>([\s\S]*?)</think>", raw_content)
        if think_match:
            thinking_str = native_thinking or think_match.group(1).strip()
            clean_content = re.sub(r"<think>[\s\S]*?</think>", "", raw_content).strip()
        elif "<think>" in raw_content:
            parts = raw_content.split("<think>", 1)
            clean_content = parts[0].strip()
            thinking_str = native_thinking or parts[1].strip()
        else:
            thinking_str = native_thinking
            clean_content = raw_content

        last_assistant_content = clean_content

        if thinking_str:
            emit_event("thought", {"content": thinking_str})
        if clean_content and not raw_tool_calls:
            emit_event("thought", {"content": clean_content})

        # Parse tool calls (native or text fallback)
        parsed_tool_calls: List[Dict[str, Any]] = []
        if raw_tool_calls:
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                parsed_tool_calls.append({
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", {}),
                })
        elif clean_content:
            fallback = ToolCallParser.extract_tool_calls(clean_content)
            for fc in fallback:
                if fc.get("name") in scoped_tools:
                    parsed_tool_calls.append(fc)

        # Record assistant turn in context
        if raw_tool_calls:
            messages.append({
                "role": "assistant",
                "content": clean_content,
                "tool_calls": [
                    {"type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in parsed_tool_calls
                ],
            })
        else:
            messages.append({"role": "assistant", "content": clean_content})

        # 4. If no tool calls were made, check if yield was called; if not, trigger reminder ladder
        if not parsed_tool_calls:
            if yield_tool.called:
                break  # Finished successfully

            retry_count += 1
            if retry_count >= max_yield_retries:
                # Force final synthesis if model still refused to call yield
                yield_tool.called = True
                summary_text = clean_content or last_assistant_content or "Subagent completed without delivering structured yield."
                yield_tool.data = {"summary": summary_text}
                break

            reminder = render_yield_reminder(
                retry_count=retry_count,
                max_retries=max_yield_retries,
                budget_stop=monitor.budget_stop_requested,
            )
            messages.append({"role": "user", "content": reminder})
            continue

        # 5. Execute tool calls
        for tc in parsed_tool_calls:
            tool_name = tc.get("name", "")
            raw_args = tc.get("arguments", {})
            norm_args = ToolArgumentNormalizer.normalize(tool_name, raw_args)

            emit_event("tool_call", {"tool": tool_name, "arguments": norm_args})

            if tool_name not in scoped_tools:
                tool_res = f"Permission Denied: Tool '{tool_name}' is forbidden for subagent '{agent_definition.name}'."
            else:
                try:
                    tool_fn = scoped_tools[tool_name]
                    sig = inspect.signature(tool_fn)
                    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                    if not has_var_kw:
                        valid_params = set(sig.parameters.keys())
                        filtered_args = {k: v for k, v in norm_args.items() if k in valid_params}
                    else:
                        filtered_args = norm_args

                    if inspect.iscoroutinefunction(tool_fn):
                        tool_res = await tool_fn(**filtered_args)
                    else:
                        tool_res = await asyncio.to_thread(tool_fn, **filtered_args)
                        if inspect.iscoroutine(tool_res):
                            tool_res = await tool_res
                    tool_res = str(tool_res)
                except Exception as t_err:
                    tool_res = f"Error executing {tool_name}: {str(t_err)}"

            monitor.record_tool_call(tool_name, tool_res)
            emit_event("tool_executed", {"tool": tool_name, "result": tool_res})

            messages.append({
                "role": "tool",
                "name": tool_name,
                "content": tool_res,
            })

        # If yield was executed during this turn and is terminal, complete the run
        if yield_tool.called and yield_tool.is_terminal:
            break

    # Build final SingleResult
    final_output = json.dumps(yield_tool.data, indent=2) if yield_tool.data else last_assistant_content
    emit_event("finish", {
        "status": "completed" if not yield_tool.error else "failed",
        "report": final_output,
        "structured": yield_tool.data,
        "error": yield_tool.error,
        "tokens": monitor.total_tokens,
        "duration_ms": monitor.duration_ms,
    })

    return SingleResult(
        id=id,
        agent=agent_definition.name,
        agent_source=agent_definition.source,
        task=user_prompt,
        assignment=assignment,
        exit_code=0 if (yield_tool.called and not yield_tool.error) else 1,
        output=final_output,
        structured_output=yield_tool.data,
        error=yield_tool.error,
        duration_ms=monitor.duration_ms,
        prompt_tokens=monitor.prompt_tokens,
        completion_tokens=monitor.completion_tokens,
        total_tokens=monitor.total_tokens,
        requests=monitor.requests,
        model_role=agent_definition.model,
        model_override=resolved_model,
        worktree_path=worktree_path,
    )
