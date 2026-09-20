import inspect
import json
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set, Callable
import ollama

from config.settings import OLLAMA_HOST, DEFAULT_MODEL_ID
from tools.parser import ToolCallParser
from plugins.argument_normalizer import ToolArgumentNormalizer
from tools.schemas import TOOL_SCHEMAS
from context.manager import ContextManager

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
        max_iterations: int = 40,
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
        self.last_run_events: List[Dict[str, Any]] = []
        self.last_run_metrics: Dict[str, Any] = {}

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

    def _build_effective_system_prompt(self) -> str:
        """Enriches the subagent's system prompt with active runtime ports and preview URLs if available."""
        if not self.tool_registry:
            return self.system_prompt

        dev_info = None
        if hasattr(self.tool_registry, "get_dev_server_info"):
            try:
                dev_info = self.tool_registry.get_dev_server_info()
            except Exception:
                dev_info = None

        if not dev_info and hasattr(self.tool_registry, "get_dev_server_url"):
            try:
                dev_url = self.tool_registry.get_dev_server_url()
                if dev_url:
                    port = dev_url.split(":")[-1] if ":" in dev_url else "3000"
                    dev_info = {"url": dev_url, "port": port, "backend_port": 5001}
            except Exception:
                pass

        if dev_info and dev_info.get("url"):
            frontend_url = dev_info.get("url")
            frontend_port = dev_info.get("port")
            backend_port = dev_info.get("backend_port", 5001)
            runtime_block = (
                f"\n\n=============================================================================\n"
                f"ACTIVE APPLICATION RUNTIME & PREVIEW ENVIRONMENT:\n"
                f"=============================================================================\n"
                f"- Frontend Preview URL: {frontend_url} (Port {frontend_port})\n"
                f"- Backend API Port: {backend_port} (`process.env.BACKEND_PORT || {backend_port}`, API URL: http://localhost:{backend_port})\n"
                f"============================================================================="
            )
            return f"{self.system_prompt}{runtime_block}"

        return self.system_prompt

    def run(self, task_description: str) -> str:
        """
        Executes the autonomous child agent loop synchronously.
        (Called via asyncio.to_thread in CodingHarness).
        """
        self.last_run_events.clear()
        self.last_run_metrics.clear()

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_duration_ms = 0.0

        def emit_event(event_data: Dict[str, Any]):
            payload = {
                "type": "subagent_event",
                "subagent": self.name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **event_data,
            }
            self.last_run_events.append(dict(payload))
            if self.event_callback:
                try:
                    self.event_callback(payload)
                except Exception as cb_err:
                    logger.warning(f"[{self.name}] Event callback error: {cb_err}")

        effective_system_prompt = self._build_effective_system_prompt()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": effective_system_prompt},
            {"role": "user", "content": task_description},
        ]

        scoped_schemas = self._get_scoped_schemas()
        scoped_tools = self._get_scoped_tool_map()

        try:
            client = ollama.Client(host=OLLAMA_HOST)
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to create Ollama client: {e}")
            return f"Error: Unable to connect to Ollama at {OLLAMA_HOST}."

        emit_event({
            "event": "start",
            "task": task_description,
            "model": self.model_name,
            "max_iterations": self.max_iterations,
        })

        last_content: str = ""
        debug_payload: Optional[Dict[str, Any]] = None

        for iteration in range(1, self.max_iterations + 1):
            emit_event({
                "event": "iteration_start",
                "iteration": iteration,
                "max_iterations": self.max_iterations,
            })

            # In-loop context squashing: truncate older verbose tool outputs (>2 turns old) to keep context lean
            if iteration > 2 and len(messages) > 6:
                for old_m in messages[2:-4]:
                    if old_m.get("role") in ["tool", "user"]:
                        c = old_m.get("content", "")
                        if isinstance(c, str) and len(c) > 1200:
                            old_m["content"] = f"{c[:1000]}\n... [truncated older output for context efficiency]"

            messages_sent_snapshot = [dict(m) for m in messages]

            try:
                response = client.chat(
                    model=self.model_name,
                    messages=messages,
                    tools=scoped_schemas if scoped_schemas else None,
                    options={"temperature": 0.5, "num_ctx": 16384},
                )
            except Exception as e:
                logger.error(f"[{self.name}] Ollama chat error on iteration {iteration}: {e}")
                err_res = f"Subagent execution failed due to model error: {str(e)}"
                emit_event({
                    "event": "finish",
                    "status": "error",
                    "report": err_res,
                })
                return err_res

            # Extract token counts and durations from Ollama
            p_tokens = response.get("prompt_eval_count") or 0
            c_tokens = response.get("eval_count") or 0
            dur_ms = round((response.get("total_duration") or 0) / 1e6, 2)
            total_prompt_tokens += p_tokens
            total_completion_tokens += c_tokens
            total_duration_ms += dur_ms

            assistant_msg = response.get("message", {})
            raw_content = assistant_msg.get("content", "") or ""
            native_thinking = assistant_msg.get("thinking", "") or ""
            raw_tool_calls = assistant_msg.get("tool_calls", [])

            # Separate thinking tags (<think>...</think>) if present (DeepSeek-R1, reasoning models)
            think_match = re.search(r"<think>([\s\S]*?)</think>", raw_content)
            if think_match:
                extracted_think = think_match.group(1).strip()
                clean_content = re.sub(r"<think>[\s\S]*?</think>", "", raw_content).strip()
                thinking_str = native_thinking or extracted_think
            else:
                thinking_str = native_thinking
                clean_content = raw_content

            last_content = clean_content

            # 1. Parse native tool calls
            parsed_tool_calls: List[Dict[str, Any]] = []
            is_native_tool_call = bool(raw_tool_calls)
            if raw_tool_calls:
                for tc in raw_tool_calls:
                    fn = tc.get("function", {})
                    parsed_tool_calls.append({
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments", {}),
                    })

            # 2. Text fallback parser if model output tool call as raw text/JSON
            if not parsed_tool_calls and clean_content:
                fallback_calls = ToolCallParser.extract_tool_calls(clean_content)
                for fc in fallback_calls:
                    if fc.get("name") in self.allowed_tools:
                        parsed_tool_calls.append(fc)

            # Build transparent debug payload for this iteration
            iteration_metrics = {
                "prompt_eval_count": p_tokens,
                "eval_count": c_tokens,
                "duration_ms": dur_ms,
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "total_duration_ms": round(total_duration_ms, 2),
            }
            debug_payload = {
                "iteration": iteration,
                "model": self.model_name,
                "messages_sent": messages_sent_snapshot,
                "llm_response": {
                    "content": clean_content,
                    "thinking": thinking_str,
                    "tool_calls": parsed_tool_calls,
                },
                "metrics": iteration_metrics,
            }

            # Emit thinking if present
            if thinking_str:
                emit_event({
                    "event": "thought",
                    "content": thinking_str,
                    "iteration": iteration,
                    "debug": debug_payload,
                    "metrics": iteration_metrics,
                })

            # Emit conversational thought only if not pure tool call JSON
            is_pure_tool_json = bool(
                parsed_tool_calls
                and not thinking_str
                and (
                    clean_content.strip().startswith("{")
                    or clean_content.strip().startswith("```")
                    or clean_content.strip().startswith("<tool")
                )
            )
            if clean_content and not is_pure_tool_json:
                emit_event({
                    "event": "thought",
                    "content": clean_content,
                    "iteration": iteration,
                    "debug": debug_payload,
                    "metrics": iteration_metrics,
                })

            # 3. If no tool calls made, the subagent has reached its final diagnosis/output
            if not parsed_tool_calls:
                messages.append({"role": "assistant", "content": clean_content})
                final_res = clean_content.strip() if clean_content.strip() else "Subagent completed without textual output."
                self.last_run_metrics = {
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "total_tokens": total_prompt_tokens + total_completion_tokens,
                    "total_duration_ms": round(total_duration_ms, 2),
                    "iterations": iteration,
                    "model": self.model_name,
                }
                emit_event({
                    "event": "finish",
                    "status": "completed",
                    "report": final_res,
                    "debug": debug_payload,
                    "metrics": self.last_run_metrics,
                })
                return final_res

            # 4. Record assistant message with tool calls in child context
            if is_native_tool_call:
                messages.append({
                    "role": "assistant",
                    "content": clean_content or "",
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
            else:
                # Text fallback tool call: preserve the assistant's content containing the tool call JSON
                messages.append({
                    "role": "assistant",
                    "content": clean_content,
                })

            # 5. Execute child tool calls (enforcing strict security whitelist)
            for tc in parsed_tool_calls:
                tool_name = tc.get("name", "")
                raw_args = tc.get("arguments", {})

                # Normalize arguments
                norm_args = ToolArgumentNormalizer.normalize(tool_name, raw_args)

                # Emit tool call intent
                emit_event({
                    "event": "tool_call",
                    "tool": tool_name,
                    "arguments": norm_args,
                    "iteration": iteration,
                    "debug": debug_payload,
                    "metrics": iteration_metrics,
                })

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
                        sig = inspect.signature(tool_fn)
                        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                        if not has_var_keyword:
                            valid_params = set(sig.parameters.keys())
                            filtered_args = {k: v for k, v in norm_args.items() if k in valid_params}
                        else:
                            filtered_args = norm_args
                        result = tool_fn(**filtered_args)
                        result = str(result)
                    except Exception as e:
                        result = f"Error executing {tool_name}: {str(e)}"

                # Add corrective guidance if tool returned an error
                if result.startswith("Error:"):
                    result += f"\n[Guidance: If a file path was not found or failed, use glob_files or list_directory to verify valid workspace paths.]"

                # Emit step progress
                emit_event({
                    "event": "tool_executed",
                    "tool": tool_name,
                    "iteration": iteration,
                    "arguments": norm_args,
                    "result": result[:2000] if len(result) > 2000 else result,
                    "debug": debug_payload,
                    "metrics": iteration_metrics,
                })

                project_root = getattr(self.tool_registry, "sandbox_path", None)
                ContextManager.record_tool_result(
                    messages=messages,
                    tool_name=tool_name,
                    result=result,
                    project_root=project_root,
                    is_native_tool_call=is_native_tool_call,
                )

        # Safety fallback if loop exhausted max_iterations
        final_res = (
            last_content.strip()
            if last_content.strip()
            else f"Subagent '{self.name}' reached safety iteration limit ({self.max_iterations}) without final conclusion."
        )
        self.last_run_metrics = {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "total_duration_ms": round(total_duration_ms, 2),
            "iterations": self.max_iterations,
            "model": self.model_name,
        }
        emit_event({
            "event": "finish",
            "status": "limit_reached",
            "report": final_res,
            "debug": debug_payload,
            "metrics": self.last_run_metrics,
        })
        return final_res
