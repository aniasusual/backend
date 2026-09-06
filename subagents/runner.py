import json
import logging
from typing import Dict, Any, List, Optional, Set, Callable
import ollama

from config.settings import OLLAMA_HOST, DEFAULT_MODEL_ID
from tools.parser import ToolCallParser
from plugins.argument_normalizer import ToolArgumentNormalizer
from tools.schemas import TOOL_SCHEMAS

logger = logging.getLogger(__name__)


class SubagentRunner:
    """
    Autonomous Child-Loop Subagent Runner.
    Inspired by Emergent's Cortex child agent execution architecture.

    Features:
    1. Context Isolation: Runs with its own private message history; does not pollute the parent agent's tokens.
    2. Scoped Tool Whitelist: Strictly permits only designated tools (e.g. read-only tools for troubleshooters).
    3. Tool Schema Scoping: Only sends the JSON schemas of allowed tools to Ollama.
    4. Execution Budget: Enforces max_iterations to guarantee termination.
    5. Event Telemetry: Emits subagent events to the UI via event_callback.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        allowed_tools: Set[str],
        model_name: str = DEFAULT_MODEL_ID,
        max_iterations: int = 8,
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.allowed_tools = set(allowed_tools)
        self.model_name = model_name
        self.max_iterations = max_iterations
        self.tool_registry = tool_registry
        self.event_callback = event_callback

    def _get_scoped_schemas(self) -> List[Dict[str, Any]]:
        """Filters global tool schemas to only include tools in allowed_tools."""
        scoped: List[Dict[str, Any]] = []
        for s in TOOL_SCHEMAS:
            if not isinstance(s, dict):
                continue
            fn = s.get("function")
            if isinstance(fn, dict):
                name = fn.get("name")
                if isinstance(name, str) and name in self.allowed_tools:
                    scoped.append(s)
        return scoped

    def _get_scoped_tool_map(self) -> Dict[str, Callable]:
        """Filters tool registry functions to only include tools in allowed_tools."""
        if not self.tool_registry:
            return {}
        all_tools = self.tool_registry.get_tools()
        return {k: v for k, v in all_tools.items() if k in self.allowed_tools}

    def run(self, task_description: str) -> str:
        """
        Executes the autonomous child agent loop synchronously.
        (Called via asyncio.to_thread in CodingHarness).
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task_description},
        ]

        scoped_schemas = self._get_scoped_schemas()
        scoped_tools = self._get_scoped_tool_map()

        try:
            client = ollama.Client(host=OLLAMA_HOST)
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to create Ollama client: {e}")
            return f"Error: Unable to connect to Ollama at {OLLAMA_HOST}."

        last_content: str = ""
        for iteration in range(1, self.max_iterations + 1):
            if self.event_callback:
                self.event_callback({
                    "type": "subagent_event",
                    "subagent": self.name,
                    "event": "iteration_start",
                    "iteration": iteration,
                    "max_iterations": self.max_iterations,
                })

            try:
                response = client.chat(
                    model=self.model_name,
                    messages=messages,
                    tools=scoped_schemas if scoped_schemas else None,
                    options={"temperature": 0.0},
                )
            except Exception as e:
                logger.error(f"[{self.name}] Ollama chat error on iteration {iteration}: {e}")
                return f"Subagent execution failed due to model error: {str(e)}"

            assistant_msg = response.get("message", {})
            content = assistant_msg.get("content", "") or ""
            last_content = content
            raw_tool_calls = assistant_msg.get("tool_calls", [])

            # 1. Parse native tool calls
            parsed_tool_calls: List[Dict[str, Any]] = []
            if raw_tool_calls:
                for tc in raw_tool_calls:
                    fn = tc.get("function", {})
                    parsed_tool_calls.append({
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments", {}),
                    })

            # 2. Text fallback parser if model output tool call as raw text/JSON
            if not parsed_tool_calls and content:
                fallback_calls = ToolCallParser.extract_tool_calls(content)
                for fc in fallback_calls:
                    if fc.get("name") in self.allowed_tools:
                        parsed_tool_calls.append(fc)

            # 3. If no tool calls made, the subagent has reached its final diagnosis/output
            if not parsed_tool_calls:
                messages.append({"role": "assistant", "content": content})
                return content.strip() if content.strip() else "Subagent completed without textual output."

            # 4. Record assistant message with tool calls in child context
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    }
                    for tc in parsed_tool_calls
                ],
            })

            # 5. Execute child tool calls (enforcing strict security whitelist)
            for tc in parsed_tool_calls:
                tool_name = tc.get("name", "")
                raw_args = tc.get("arguments", {})

                # Normalize arguments
                norm_args = ToolArgumentNormalizer.normalize(tool_name, raw_args)

                # Security check: strict tool boundary enforcement
                if tool_name not in self.allowed_tools:
                    result = (
                        f"Permission Denied: Tool '{tool_name}' is forbidden for subagent '{self.name}'. "
                        f"You may ONLY call: {sorted(list(self.allowed_tools))}."
                    )
                elif tool_name not in scoped_tools:
                    result = f"Error: Tool '{tool_name}' is not registered in the subagent environment."
                else:
                    try:
                        tool_fn = scoped_tools[tool_name]
                        result = tool_fn(**norm_args)
                        result = str(result)
                    except Exception as e:
                        result = f"Error executing {tool_name}: {str(e)}"

                # Emit step progress
                if self.event_callback:
                    self.event_callback({
                        "type": "subagent_event",
                        "subagent": self.name,
                        "event": "tool_executed",
                        "tool": tool_name,
                        "iteration": iteration,
                    })

                # Append tool result to child message history
                messages.append({
                    "role": "tool",
                    "name": tool_name,
                    "content": result,
                })

        # Safety fallback if loop exhausted max_iterations
        return (
            last_content.strip()
            if last_content.strip()
            else f"Subagent '{self.name}' reached safety iteration limit ({self.max_iterations}) without final conclusion."
        )
