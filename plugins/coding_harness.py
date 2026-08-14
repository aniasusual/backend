from typing import AsyncGenerator, Dict, Any, List
import ollama
import asyncio

from plugins.base import BaseHarness
from config.prompts import CODING_SYSTEM_PROMPT
from tools.schemas import TOOL_SCHEMAS
from tools.parser import ToolCallParser
from utils.context_manager import ContextManager
from utils.stream_normalizer import UniversalStreamNormalizer

DEFAULT_MODEL = "qwen2.5-coder:7b"
MAX_ITERATIONS = 50
MAX_DISPLAY_RESULT_LEN = 500


class CodingHarness(BaseHarness):
    """
    The primary Lowkey harness — runs a full agentic loop where the LLM
    decides which tools to call, executes them, and iterates until done.
    Maintains conversation context across turns.
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

        tool_map = registry.get_tools()
        model_name = context.get("model", self.model_name)

        # Retrieve or initialize persistent message history
        messages: List[Dict[str, Any]] = context.get("messages", [])
        messages = ContextManager.prepare_messages(
            user_prompt=user_prompt,
            system_prompt=CODING_SYSTEM_PROMPT,
            existing_messages=messages,
        )

        try:
            client = ollama.AsyncClient()

            for _ in range(MAX_ITERATIONS):
                stream = await client.chat(
                    model=model_name,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    options={"temperature": 0.0},
                    stream=True
                )

                class MockMessage:
                    content = ""
                    tool_calls = None

                assistant_message = MockMessage()
                normalizer = UniversalStreamNormalizer()

                async for chunk in stream:
                    # 1. Native reasoning field (Ollama, DeepSeek, Claude 3.7)
                    if hasattr(chunk.message, "thinking") and chunk.message.thinking:
                        evt = normalizer.feed_native_thinking(chunk.message.thinking)
                        if evt:
                            yield evt

                    # 2. Structured tool calls from provider
                    if chunk.message.tool_calls:
                        if assistant_message.tool_calls is None:
                            assistant_message.tool_calls = []
                        assistant_message.tool_calls.extend(chunk.message.tool_calls)

                    # 3. Content tokens (reasoning, tool JSON, or conversational output)
                    if chunk.message.content:
                        assistant_message.content += chunk.message.content
                        for evt in normalizer.feed_content(chunk.message.content):
                            yield evt

                # Finalize turn with normalizer
                post_events, extracted_tools = normalizer.finalize()
                for evt in post_events:
                    yield evt

                # Extract tool calls (structured or parsed from text)
                if assistant_message.tool_calls:
                    tool_calls = [
                        {"name": tc.function.name, "arguments": tc.function.arguments}
                        for tc in assistant_message.tool_calls
                    ]
                else:
                    tool_calls = extracted_tools

                if not tool_calls:
                    # Final turn (no tools to run) - clean message history
                    clean_content = UniversalStreamNormalizer.extract_clean_final_text(assistant_message.content)
                    if clean_content:
                        messages.append({
                            "role": "assistant",
                            "content": clean_content,
                        })
                    yield {"type": "status", "content": "Done"}
                    return

                # Record assistant message in conversation history with structured tool_calls
                # This keeps Ollama's ChatML template valid and prevents hallucinated <tool_response> tags
                formatted_tool_calls = []
                for tc in tool_calls:
                    args = tc.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            import json
                            args = json.loads(args)
                        except Exception:
                            args = {}
                    formatted_tool_calls.append({
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": args,
                        }
                    })

                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": formatted_tool_calls,
                })

                # Execute all requested tools
                async for event in self._execute_tool_calls(tool_calls, tool_map, messages):
                    yield event

            yield {
                "type": "status",
                "content": f"Stopped after {MAX_ITERATIONS} iterations (safety limit).",
            }

        except ollama.ResponseError as e:
            yield {
                "type": "status",
                "content": f"Ollama Error: {e.error}. Ensure Ollama is running and model '{model_name}' is pulled.",
            }
        except Exception as e:
            yield {"type": "status", "content": f"Error: {str(e)}"}

    def _extract_tool_calls(self, assistant_message: Any) -> List[Dict[str, Any]]:
        """Extract tool calls either from structured response or text fallback."""
        if assistant_message.tool_calls:
            return [
                {"name": tc.function.name, "arguments": tc.function.arguments}
                for tc in assistant_message.tool_calls
            ]
        if assistant_message.content:
            return ToolCallParser.extract_tool_calls(assistant_message.content)
        return []

    async def _execute_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        tool_map: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Executes a list of tool calls, yields frontend events, and updates conversation history."""
        for tool_call in tool_calls:
            func_name = tool_call.get("name", "")
            func_args = tool_call.get("arguments", {})

            yield {
                "type": "tool_call",
                "name": func_name,
                "arguments": func_args,
            }

            result = await asyncio.to_thread(self._run_tool, func_name, func_args, tool_map)
            display_result = self._format_display_result(result)

            yield {
                "type": "tool_result",
                "name": func_name,
                "result": display_result,
            }

            tool_msg_content = result if isinstance(result, str) else str(result)
            messages.append({"role": "tool", "content": tool_msg_content})

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
    def _format_display_result(result: str) -> str:
        """Truncates long tool result strings for UI presentation."""
        if len(result) <= MAX_DISPLAY_RESULT_LEN:
            return result
        return f"{result[:MAX_DISPLAY_RESULT_LEN]}\n... ({len(result)} chars total)"
