from typing import AsyncGenerator, Dict, Any, List
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
from context import ContextManager
from utils.stream_normalizer import StreamEventDispatcher
from plugins.argument_normalizer import ToolArgumentNormalizer
from project_manager.chat_history import ChatHistoryManager

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_MAX_ITERATIONS = 50
MAX_DISPLAY_RESULT_LEN = 500


class CodingHarness(BaseHarness):
    """
    The primary Lowkey harness — runs a full agentic loop dynamically tailored
    by model-specific YAML profiles (tool whitelists, subagents, and reasoning configurations).
    """

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

        # Resolve model-specific AgentProfile from YAML specs
        profile = AgentLoader.get_profile_for_model(model_name)
        callable_tools = profile.all_callable_tools

        # Expose all registered tools, subagents, and schemas universally to every model
        tool_map = registry.get_tools()
        active_schemas = list(TOOL_SCHEMAS.values() if isinstance(TOOL_SCHEMAS, dict) else TOOL_SCHEMAS)

        # Primary system prompt dynamically resolved for the active model profile
        system_prompt = get_system_prompt_for_profile(profile.prompt_id)

        # Append reasoning fallback guide for thinking/reasoning models (DeepSeek-R1)
        if profile.is_reasoning_model:
            system_prompt = f"{system_prompt}\n\n{REASONING_MODEL_TOOL_FALLBACK}"

        # Retrieve or initialize persistent message history
        messages: List[Dict[str, Any]] = context.get("messages", [])
        messages = ContextManager.prepare_messages(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            existing_messages=messages,
            model_name=model_name,
        )

        turn_start_idx = max(0, len(messages) - 1)
        turn_ui_events: List[Dict[str, Any]] = [
            {
                "type": "user",
                "role": "user",
                "content": user_prompt,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
        accumulated_thinking: List[str] = []

        try:
            client = ollama.AsyncClient()

            for _ in range(profile.max_iterations):
                # Tier 1 in-loop squashing: prune older tool outputs before next model turn
                ContextManager.maybe_squash(messages, model_name=model_name)

                stream = await client.chat(
                    model=model_name,
                    messages=messages,
                    tools=active_schemas if active_schemas else None,
                    options={"temperature": 0.0},
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

                # Flush any thinking into turn_ui_events
                if accumulated_thinking:
                    turn_ui_events.append({
                        "type": "thinking",
                        "content": "".join(accumulated_thinking).strip(),
                        "collapsed": True,
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

                # Normalize arguments so they are always valid dictionaries (never raw lists)
                tool_calls: List[Dict[str, Any]] = []
                for tc in raw_tool_calls:
                    if isinstance(tc, dict):
                        fn_name = tc.get("name", "")
                        fn_args = self._normalize_tool_arguments(fn_name, tc.get("arguments", {}))
                        tool_calls.append({"name": fn_name, "arguments": fn_args})

                if not tool_calls:
                    # Final turn (no tools to run) - clean message history
                    clean_content = StreamEventDispatcher.extract_clean_final_text(assistant_content)
                    if clean_content and clean_content.strip():
                        messages.append({
                            "role": "assistant",
                            "content": clean_content.strip(),
                        })
                        turn_ui_events.append({
                            "type": "token",
                            "content": clean_content.strip(),
                        })
                    turn_ui_events.append({"type": "status", "content": "Done"})
                    self._persist_turn(
                        context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name
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
                        "content": assistant_content or "",
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
                async for event in self._execute_tool_calls(tool_calls, tool_map, messages, context, is_native_tool_call):
                    turn_ui_events.append(dict(event))
                    yield event

                if has_terminal_tool:
                    turn_ui_events.append({"type": "status", "content": "Done"})
                    self._persist_turn(
                        context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name
                    )
                    yield {"type": "status", "content": "Done"}
                    return

            stop_evt = {
                "type": "status",
                "content": f"Stopped after {profile.max_iterations} iterations (safety limit).",
            }
            turn_ui_events.append(stop_evt)
            self._persist_turn(
                context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name
            )
            yield stop_evt

        except ollama.ResponseError as e:
            err_msg = f"Ollama Error: {e.error}. Ensure Ollama is running and model '{model_name}' is pulled."
            turn_ui_events.append({"type": "status", "content": err_msg})
            self._persist_turn(
                context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, status="error"
            )
            yield {"type": "status", "content": err_msg}
        except Exception as e:
            err_msg = f"Error: {str(e)}"
            turn_ui_events.append({"type": "status", "content": err_msg})
            self._persist_turn(
                context, user_prompt, turn_ui_events, messages[turn_start_idx:], model_name, status="error"
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
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Executes a list of tool calls, yields frontend events, and updates conversation history."""
        request_approval = context.get("request_approval")

        for tool_call in tool_calls:
            func_name = tool_call.get("name", "")
            func_args = tool_call.get("arguments", {})

            yield {
                "type": "tool_call",
                "name": func_name,
                "arguments": func_args,
            }

            if func_name in ["execute_command", "run_background_command"] and request_approval:
                command = func_args.get("command", "")
                reason = func_args.get("reason", "No reason provided")
                
                approved = await request_approval(command, reason)
                if not approved:
                    result = "User denied this command. Please rethink your approach or ask the user for guidance."
                    yield {
                        "type": "tool_result",
                        "name": func_name,
                        "result": result,
                    }
                    if is_native_tool_call:
                        messages.append({"role": "tool", "name": func_name, "content": result})
                    else:
                        messages.append({
                            "role": "user",
                            "content": f"[Tool Result for '{func_name}']:\n{result}\n\nPlease proceed with the next step."
                        })
                    continue

            result = await asyncio.to_thread(self._run_tool, func_name, func_args, tool_map)
            display_result = self._format_display_result(result)

            yield {
                "type": "tool_result",
                "name": func_name,
                "result": display_result,
            }

            tool_msg_content = result if isinstance(result, str) else str(result)
            if is_native_tool_call:
                messages.append({"role": "tool", "name": func_name, "content": tool_msg_content})
            else:
                next_prompt_guidance = (
                    "Design system applied! Now proceed to write the Express API in server/index.js and React UI in src/App.jsx using write_file or write_files. Do NOT call finish yet!"
                    if func_name in ["invoke_design_agent", "design_agent"]
                    else "Tool execution completed. Please proceed with the next step in the engineering lifecycle."
                )
                messages.append({
                    "role": "user",
                    "content": f"[Tool Result for '{func_name}']:\n{tool_msg_content}\n\n{next_prompt_guidance}"
                })

    @staticmethod
    def _run_tool(name: str, args: Dict[str, Any], tool_map: Dict[str, Any]) -> str:
        """Invokes the specified tool function safely."""
        if name not in tool_map:
            return f"Error: Unknown tool '{name}'"
        try:
            return str(tool_map[name](**args))
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
        status: str = "completed",
    ) -> None:
        """Persists turn data to project chat history (.lowkey_chat.json)."""
        project = context.get("project")
        if not project or not hasattr(project, "path"):
            return

        try:
            turn_record = {
                "turn_id": f"turn_{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "clean_user_prompt": user_prompt.strip(),
                "model": model_name,
                "status": status,
                "ui_events": ui_events,
                "llm_messages": llm_messages,
            }
            ChatHistoryManager.save_turn(project.path, turn_record)
        except Exception as e:
            print(f"[CodingHarness] Error saving turn to chat history: {e}")
