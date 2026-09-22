from typing import AsyncGenerator, Dict, Any, List, Optional
import copy
import inspect


import asyncio
import uuid
from datetime import datetime, timezone
import ollama

from plugins.base import BaseHarness
from config.prompts import (
    NODE_REACT_SYSTEM_PROMPT,
    REASONING_MODEL_TOOL_FALLBACK,
    get_system_prompt_for_profile,
)
from config.agent_loader import AgentLoader, AgentProfile
from tools.schemas import TOOL_SCHEMAS
from tools.parser import ToolCallParser
from context import ContextManager, ContextConfig, StaticLayerManager, ContextSquasher
from utils.stream_normalizer import StreamEventDispatcher
from plugins.argument_normalizer import ToolArgumentNormalizer
from project_manager.chat_history import ChatHistoryManager

DEFAULT_MODEL = "qwen2.5-coder:14b"
DEFAULT_MAX_ITERATIONS = 100
MAX_DISPLAY_RESULT_LEN = 500


class CodingHarness(BaseHarness):
    """
    The primary Lowkey harness — runs a full agentic loop dynamically tailored
    by model-specific YAML profiles (tool whitelists, subagents, and reasoning configurations).
    """

    @staticmethod
    def _build_runtime_context(dev_info: Optional[Dict[str, Any]]) -> str:
        """Builds standardized Markdown block documenting active ports and preview environment."""
        if not dev_info or not dev_info.get("url"):
            return ""
        frontend_url = dev_info.get("url")
        frontend_port = dev_info.get("port")
        backend_port = dev_info.get("backend_port", 5001)
        return (
            f"\n\n=============================================================================\n"
            f"ACTIVE APPLICATION RUNTIME & PREVIEW ENVIRONMENT:\n"
            f"=============================================================================\n"
            f"- Frontend Preview URL: {frontend_url} (Port {frontend_port})\n"
            f"- Backend API Port: {backend_port} (`process.env.BACKEND_PORT || {backend_port}`, API URL: http://localhost:{backend_port})\n"
            f"- Automated UI Testing: `invoke_testing_agent(instructions=\"...\")` automatically tests {frontend_url}.\n"
            f"- Backend API Testing: Test endpoints via `execute_command(command=\"curl -s http://localhost:{backend_port}/api/...\")`.\n"
            f"============================================================================="
        )

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name

    async def process_prompt(
        self, user_prompt: str, context: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        registry = context.get("registry")
        if not registry:
            yield {"type": "status", "content": "Error: No tool registry available."}
            return

        model_name = context.get("model", self.model_name)

        # Synchronize active model across tool registry and all child subagents
        if hasattr(registry, "set_model_name"):
            registry.set_model_name(model_name)

        # Resolve model-specific AgentProfile from YAML specs
        profile = AgentLoader.get_profile_for_model(model_name)
        callable_tools = profile.all_callable_tools

        # Dynamic tool filtering: support context override or profile whitelisting
        custom_tools = context.get("allowed_tools")
        allowed_tool_names = set(custom_tools) if custom_tools is not None else set(callable_tools)

        # Expose only whitelisted tools and schemas to the model
        tool_map = {k: v for k, v in registry.get_tools().items() if k in allowed_tool_names}
        use_native_tools = profile.supports_native_tools
        all_schemas = list(TOOL_SCHEMAS.values() if isinstance(TOOL_SCHEMAS, dict) else TOOL_SCHEMAS)
        active_schemas = [
            s for s in all_schemas
            if isinstance(s, dict) and s.get("function", {}).get("name") in allowed_tool_names
        ] if use_native_tools else None

        # Resolve project root from tool registry or context
        project_root = getattr(registry, "sandbox_path", None) or context.get("project_path")

        # Primary base system prompt dynamically resolved for the active model profile
        base_prompt = get_system_prompt_for_profile(profile.prompt_id)

        # Dynamically inject active development server runtime ports and URLs if available
        dev_info = registry.get_dev_server_info() if (registry and hasattr(registry, "get_dev_server_info")) else None
        if not dev_info and registry and hasattr(registry, "get_dev_server_url"):
            try:
                dev_url = registry.get_dev_server_url()
                if dev_url:
                    dev_info = {"url": dev_url, "port": dev_url.split(":")[-1] if ":" in dev_url else 3000, "backend_port": 5001}
            except Exception:
                pass

        runtime_context = self._build_runtime_context(dev_info)
        reasoning_fallback = REASONING_MODEL_TOOL_FALLBACK if not use_native_tools else None

        # Assemble comprehensive Static Layer prompt (identity + discovered repository rules + runtime ports + tool fallback)
        system_prompt = StaticLayerManager.build_static_prompt(
            base_prompt=base_prompt,
            project_root=project_root,
            runtime_context=runtime_context,
            reasoning_fallback=reasoning_fallback,
        )

        # Retrieve or initialize persistent message history
        messages: List[Dict[str, Any]] = context.get("messages", [])
        mounted_ram = getattr(registry, "mounted_virtual_ram", {})
        messages = ContextManager.prepare_messages(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            existing_messages=messages,
            model_name=model_name,
            tools=active_schemas if active_schemas else None,
            project_root=project_root,
            mounted_virtual_ram=mounted_ram,
        )

        turn_start_idx = max(0, len(messages) - 1)
        turn_id = f"turn_{uuid.uuid4().hex[:8]}"
        turn_ui_events: List[Dict[str, Any]] = [
            {
                "type": "user",
                "role": "user",
                "content": user_prompt,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
        accumulated_thinking: List[str] = []

        # Immediately persist user prompt so turn is registered even if cancelled early
        self._persist_turn(
            context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, turn_id=turn_id, status="in_progress"
        )

        # Context configuration: allow explicit context override, otherwise dynamically resolve for active model
        context_config = context.get("context_config")
        if not context_config:
            context_config = ContextConfig.for_model(model_name)
        if context.get("context_window"):
            try:
                context_config.context_window = int(context["context_window"])
            except (ValueError, TypeError):
                pass

        # Emit initial turn context telemetry immediately upon turn preparation
        initial_telemetry = ContextManager.get_context_telemetry(
            messages,
            model_name=model_name,
            tools=active_schemas if active_schemas else None,
            mounted_virtual_ram=mounted_ram,
            config=context_config,
        )
        yield {
            "type": "context_telemetry",
            "telemetry": initial_telemetry,
        }
        yield {"type": "status", "content": "Running"}
        try:
            client = ollama.AsyncClient()

            for iteration_idx in range(profile.max_iterations):
                # Tier 1 in-loop squashing: prune older tool outputs and sync virtual RAM before next model turn
                active_ram = getattr(registry, "mounted_virtual_ram", {})
                was_applied, was_squashed, was_evicted, was_rolled_up = ContextManager.maybe_squash(
                    messages,
                    model_name=model_name,
                    config=context_config,
                    tools=active_schemas if active_schemas else None,
                    mounted_virtual_ram=active_ram,
                    return_details=True,
                )

                # Real-time iteration context telemetry
                iter_telemetry = ContextManager.get_context_telemetry(
                    messages,
                    model_name=model_name,
                    tools=active_schemas if active_schemas else None,
                    mounted_virtual_ram=active_ram,
                    config=context_config,
                    squashed=was_squashed,
                    evicted=was_evicted,
                    rolled_up=was_rolled_up,
                )
                yield {
                    "type": "context_telemetry",
                    "telemetry": iter_telemetry,
                }
                # Snapshot the exact messages sent to the model for this iteration (deep copy for 100% wire fidelity)
                messages_sent_snapshot = copy.deepcopy(messages)

                stream = await client.chat(
                    model=model_name,
                    messages=messages,
                    tools=active_schemas if active_schemas else None,
                    options={
                        "temperature": 0.5,
                        "num_ctx": context_config.context_window,
                    },
                    stream=True
                )

                assistant_content = ""
                assistant_tool_calls: List[Any] = []
                dispatcher = StreamEventDispatcher()

                async for chunk in stream:
                    # 1. Native reasoning field (Ollama, DeepSeek, Claude 3.7)
                    if hasattr(chunk.message, "thinking") and chunk.message.thinking:
                        accumulated_thinking.append(chunk.message.thinking)
                        evt = dispatcher.handle_thinking(chunk.message.thinking)
                        if evt:
                            yield evt

                    # 2. Structured native tool calls from provider
                    if chunk.message.tool_calls:
                        assistant_tool_calls.extend(chunk.message.tool_calls)

                    # 3. Content tokens (conversational text or fallback JSON)
                    if chunk.message.content:
                        assistant_content += chunk.message.content
                        for evt in dispatcher.handle_content(chunk.message.content):
                            yield evt

                raw_thinking_str = "".join(accumulated_thinking).strip() if accumulated_thinking else ""

                # Flush any thinking into turn_ui_events
                if accumulated_thinking:
                    turn_ui_events.append({
                        "type": "thinking",
                        "content": raw_thinking_str,
                        "collapsed": True,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    accumulated_thinking = []

                # Extract tool calls (native structured or parser fallback)
                raw_tool_calls = []
                is_native_tool_call = bool(assistant_tool_calls)
                if is_native_tool_call:
                    raw_tool_calls = [
                        {"name": tc.function.name, "arguments": tc.function.arguments}
                        for tc in assistant_tool_calls
                    ]
                else:
                    raw_tool_calls = dispatcher.extract_fallback_tools()

                # Build the complete, transparent debug payload for this iteration
                debug_payload = {
                    "iteration": iteration_idx + 1,
                    "model": model_name,
                    "options": {
                        "temperature": 0.5,
                        "num_ctx": context_config.context_window,
                    },
                    "context_telemetry": iter_telemetry,
                    "messages_sent": messages_sent_snapshot,
                    "llm_response": {
                        "content": assistant_content,
                        "thinking": raw_thinking_str,
                        "tool_calls": raw_tool_calls,
                    },
                }

                # Attach initial debug payload to user prompt turn if it's the first iteration
                if iteration_idx == 0 and turn_ui_events:
                    turn_ui_events[0]["debug"] = debug_payload

                # Yield real-time debug event for frontend inspector
                yield {
                    "type": "llm_debug",
                    "iteration": iteration_idx + 1,
                    "debug": debug_payload,
                }


                # Normalize arguments so they are always valid dictionaries (never raw lists)
                tool_calls: List[Dict[str, Any]] = []
                for tc in raw_tool_calls:
                    if isinstance(tc, dict):
                        fn_name = tc.get("name", "")
                        fn_args = self._normalize_tool_arguments(fn_name, tc.get("arguments", {}))
                        tool_calls.append({"name": fn_name, "arguments": fn_args})

                # Extract and persist any conversational text spoken by the assistant in this iteration
                clean_content = StreamEventDispatcher.extract_clean_final_text(assistant_content)
                if clean_content and clean_content.strip():
                    turn_ui_events.append({
                        "type": "token",
                        "content": clean_content.strip(),
                        "debug": debug_payload,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                if not tool_calls:
                    # Final turn (no tools to run) - clean message history
                    if clean_content and clean_content.strip():
                        messages.append({
                            "role": "assistant",
                            "content": clean_content.strip(),
                        })
                    final_telemetry = ContextManager.get_context_telemetry(
                        messages,
                        model_name=model_name,
                        tools=active_schemas if active_schemas else None,
                        mounted_virtual_ram=getattr(registry, "mounted_virtual_ram", {}),
                        config=context_config,
                    )
                    yield {
                        "type": "context_telemetry",
                        "telemetry": final_telemetry,
                    }
                    turn_ui_events.append({
                        "type": "status",
                        "content": "Done",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    self._persist_turn(
                        context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, turn_id=turn_id, status="completed"
                    )
                    yield {"type": "status", "content": "Done"}
                    return

                # Record assistant message in conversation history
                if is_native_tool_call:
                    formatted_tool_calls = []
                    for tc in tool_calls:
                        formatted_tool_calls.append({
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": tc.get("arguments", {}),
                            }
                        })
                    messages.append({
                        "role": "assistant",
                        "content": clean_content or "",
                        "tool_calls": formatted_tool_calls,
                    })
                else:
                    # Text fallback tool call: preserve the assistant's content containing the tool call JSON
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content,
                    })

                # Execute all requested tools
                has_terminal_tool = any(isinstance(tc, dict) and tc.get("name") in ["finish", "ask_human"] for tc in tool_calls)
                async for event in self._execute_tool_calls(
                    tool_calls, tool_map, messages, context, is_native_tool_call, debug_payload=debug_payload
                ):
                    evt_dict = dict(event)
                    turn_ui_events.append(evt_dict)
                    if evt_dict.get("type") == "tool_result" and evt_dict.get("subagentEvents"):
                        for prev_evt in reversed(turn_ui_events[:-1]):
                            if prev_evt.get("type") == "tool_call" and prev_evt.get("name") == evt_dict.get("name"):
                                prev_evt["subagentEvents"] = evt_dict["subagentEvents"]
                                prev_evt["subagentMetrics"] = evt_dict.get("subagentMetrics", {})
                                prev_evt["subagentStatus"] = "completed"
                                break
                    yield event
                # Check for settled background subagent deliveries
                async_job_mgr = getattr(registry, "async_job_manager", None)
                if async_job_mgr:
                    for delivery in async_job_mgr.consume_deliveries():
                        delivery_text = f"Background subagent `{delivery.id}` ({delivery.agent}) completed:\n{delivery.output}"
                        async_res_event = {
                            "type": "tool_result",
                            "name": "task",
                            "result": delivery_text,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "subagentStatus": "completed" if delivery.exit_code == 0 else "failed",
                        }
                        turn_ui_events.append(async_res_event)
                        messages.append({
                            "role": "user",
                            "content": delivery_text,
                        })
                        yield async_res_event

                # Incremental persistence: save progress to .lowkey_chat.json immediately after each tool batch
                self._persist_turn(
                    context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, turn_id=turn_id, status="in_progress"
                )

                if has_terminal_tool:
                    # If finish or ask_human was called and no conversational token event was recorded in this iteration,
                    # preserve the finish summary or question as an assistant token event for chat history and UI fidelity
                    if not (clean_content and clean_content.strip()):
                        finish_tc = next((tc for tc in tool_calls if isinstance(tc, dict) and tc.get("name") == "finish"), None)
                        ask_tc = next((tc for tc in tool_calls if isinstance(tc, dict) and tc.get("name") == "ask_human"), None)
                        fallback_text = ""
                        if finish_tc:
                            f_args = finish_tc.get("arguments", {})
                            summary = f_args.get("summary", "")
                            next_steps = f_args.get("next_steps")
                            fallback_text = f"{summary}\n\nNext steps:\n{next_steps}" if next_steps else summary
                        elif ask_tc:
                            a_args = ask_tc.get("arguments", {})
                            fallback_text = a_args.get("question") or a_args.get("prompt", "")

                        if fallback_text and fallback_text.strip():
                            term_token_evt = {
                                "type": "token",
                                "content": fallback_text.strip(),
                                "debug": debug_payload,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                            turn_ui_events.append(term_token_evt)
                            yield term_token_evt

                    final_telemetry = ContextManager.get_context_telemetry(
                        messages,
                        model_name=model_name,
                        tools=active_schemas if active_schemas else None,
                        mounted_virtual_ram=getattr(registry, "mounted_virtual_ram", {}),
                        config=context_config,
                    )
                    yield {
                        "type": "context_telemetry",
                        "telemetry": final_telemetry,
                    }
                    terminal_status = "AwaitingHuman" if ask_tc else "Done"
                    turn_status = "awaiting_human" if ask_tc else "completed"
                    turn_ui_events.append({
                        "type": "status",
                        "content": terminal_status,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    self._persist_turn(
                        context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, turn_id=turn_id, status=turn_status
                    )
                    yield {"type": "status", "content": terminal_status}
                    return

            final_telemetry = ContextManager.get_context_telemetry(
                messages,
                model_name=model_name,
                tools=active_schemas if active_schemas else None,
                mounted_virtual_ram=getattr(registry, "mounted_virtual_ram", {}),
                config=context_config,
            )
            yield {
                "type": "context_telemetry",
                "telemetry": final_telemetry,
            }
            stop_evt = {
                "type": "status",
                "content": f"Stopped after {profile.max_iterations} iterations (safety limit).",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            turn_ui_events.append(stop_evt)
            self._persist_turn(
                context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, turn_id=turn_id, status="completed"
            )
            yield stop_evt

        except asyncio.CancelledError:
            # Preserve in-flight work when user closes browser or disconnects
            self._persist_turn(
                context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, turn_id=turn_id, status="interrupted"
            )
            raise
        except ollama.ResponseError as e:
            err_msg = f"Ollama Error: {e.error}. Ensure Ollama is running and model '{model_name}' is pulled."
            turn_ui_events.append({
                "type": "status",
                "content": err_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._persist_turn(
                context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, turn_id=turn_id, status="error"
            )
            yield {"type": "status", "content": err_msg}
        except Exception as e:
            err_msg = f"Error: {str(e)}"
            turn_ui_events.append({
                "type": "status",
                "content": err_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._persist_turn(
                context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, turn_id=turn_id, status="error"
            )
            yield {"type": "status", "content": err_msg}

    def _extract_tool_calls(self, assistant_message: Any) -> List[Dict[str, Any]]:
        """Extract tool calls either from structured response or text fallback."""
        if hasattr(assistant_message, "tool_calls") and assistant_message.tool_calls:
            return [
                {"name": tc.function.name, "arguments": tc.function.arguments}
                for tc in assistant_message.tool_calls
            ]
        if hasattr(assistant_message, "content") and assistant_message.content:
            return ToolCallParser.extract_tool_calls(assistant_message.content)
        return []

    async def _execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        tool_map: Dict[str, Any],
        messages: List[Dict[str, Any]],
        context: Dict[str, Any],
        is_native_tool_call: bool = True,
        debug_payload: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Executes a list of tool calls, yields frontend events, and updates conversation history."""
        request_approval = context.get("request_approval")
        registry = context.get("registry")
        project_root = getattr(registry, "sandbox_path", None) or context.get("project_path")

        for idx, tool_call in enumerate(tool_calls):
            func_name = tool_call.get("name", "")
            func_args = tool_call.get("arguments", {})

            evt = {
                "type": "tool_call",
                "name": func_name,
                "arguments": func_args,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if debug_payload and idx == 0:
                evt["debug"] = debug_payload

            yield evt


            if func_name in ["execute_command", "run_background_command"] and request_approval:
                command = func_args.get("command", "")
                reason = func_args.get("reason", "No reason provided")
                
                approved = await request_approval(command, reason)
                if not approved:
                    result = "User denied this command. Please rethink your approach or ask the user for guidance."
                    denied_evt = {
                        "type": "tool_result",
                        "name": func_name,
                        "result": result,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    yield denied_evt
                    ContextManager.record_tool_result(
                        messages=messages,
                        tool_name=func_name,
                        result=result,
                        project_root=project_root,
                        is_native_tool_call=is_native_tool_call,
                    )
                    continue

            func = tool_map.get(func_name)
            if func and inspect.iscoroutinefunction(func):
                sig = inspect.signature(func)
                has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                if not has_var_keyword:
                    valid_params = set(sig.parameters.keys())
                    filtered_args = {k: v for k, v in func_args.items() if k in valid_params}
                else:
                    filtered_args = func_args
                result = await func(**filtered_args)
            else:
                result = await asyncio.to_thread(self._run_tool, func_name, func_args, tool_map)
            display_result = self._format_display_result(str(result))

            # Retrieve subagent trace and metrics for persistence and correlation
            registry = context.get("registry")
            subagent = registry.get_subagent(func_name) if (registry and hasattr(registry, "get_subagent")) else None
            subagent_events = getattr(subagent, "last_run_events", None) or []
            subagent_metrics = getattr(subagent, "last_run_metrics", None) or {}

            tool_res_event = {
                "type": "tool_result",
                "name": func_name,
                "result": display_result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if debug_payload:
                tool_res_event["debug"] = debug_payload
            if subagent_events:
                tool_res_event["subagentEvents"] = list(subagent_events)
                tool_res_event["subagentMetrics"] = dict(subagent_metrics)
                evt["subagentEvents"] = list(subagent_events)
                evt["subagentMetrics"] = dict(subagent_metrics)
                evt["subagentStatus"] = "completed"
                # Drain consumed events so they cannot leak to subsequent tools
                if hasattr(subagent, "last_run_events") and isinstance(subagent.last_run_events, list):
                    subagent.last_run_events.clear()
                if hasattr(subagent, "last_run_metrics") and isinstance(subagent.last_run_metrics, dict):
                    subagent.last_run_metrics.clear()

            yield tool_res_event

            # If dev server was started or restarted, keep system prompt in messages[0] in sync mid-turn
            if func_name in ["start_dev_server", "run_background_command"] and registry and hasattr(registry, "get_dev_server_info"):
                active_info = registry.get_dev_server_info()
                if active_info and messages and messages[0].get("role") == "system":
                    if "ACTIVE APPLICATION RUNTIME & PREVIEW ENVIRONMENT" not in messages[0]["content"]:
                        runtime_block = self._build_runtime_context(active_info)
                        if runtime_block:
                            messages[0]["content"] += runtime_block

            ContextManager.record_tool_result(
                messages=messages,
                tool_name=func_name,
                result=result,
                project_root=project_root,
                is_native_tool_call=is_native_tool_call,
            )

    @staticmethod
    def _run_tool(name: str, args: Dict[str, Any], tool_map: Dict[str, Any]) -> str:
        """Invokes the specified tool function safely."""
        if name not in tool_map:
            return f"Error: Unknown tool '{name}'"
        try:
            func = tool_map[name]
            sig = inspect.signature(func)
            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            if not has_var_keyword:
                valid_params = set(sig.parameters.keys())
                filtered_args = {k: v for k, v in args.items() if k in valid_params}
            else:
                filtered_args = args
            return str(func(**filtered_args))
        except Exception as e:
            return f"Error executing {name}: {str(e)}"

    @staticmethod
    def _normalize_tool_arguments(name: str, args: Any) -> Dict[str, Any]:
        """Ensures tool arguments are always a valid dictionary matching tool requirements across all models."""
        return ToolArgumentNormalizer.normalize(name, args)


    @staticmethod
    def _format_display_result(result: str) -> str:
        """Truncates long tool result strings for UI presentation."""
        if len(result) <= MAX_DISPLAY_RESULT_LEN:
            return result
        return f"{result[:MAX_DISPLAY_RESULT_LEN]}\n... ({len(result)} chars total)"

    @staticmethod
    def _persist_turn(
        context: Dict[str, Any],
        user_prompt: str,
        ui_events: List[Dict[str, Any]],
        llm_messages: List[Dict[str, Any]],
        model_name: str,
        turn_id: Optional[str] = None,
        status: str = "completed",
    ) -> None:
        """Persists turn data to project chat history (.lowkey_chat.json)."""
        project = context.get("project")
        if not project or not hasattr(project, "path"):
            return

        try:
            turn_record = {
                "turn_id": turn_id or f"turn_{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "clean_user_prompt": user_prompt.strip(),
                "model": model_name,
                "status": status,
                "ui_events": list(ui_events),
                "llm_messages": list(llm_messages),
            }
            ChatHistoryManager.save_turn(project.path, turn_record)
            registry = context.get("registry")
            if registry and hasattr(registry, "mounted_virtual_ram"):
                ChatHistoryManager.save_virtual_ram(project.path, getattr(registry, "mounted_virtual_ram", {}))
        except Exception as e:
            print(f"[CodingHarness] Error saving turn to chat history: {e}")
