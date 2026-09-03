import re
from typing import Any, Dict, List, Optional
from tools.parser import ToolCallParser


class StreamEventDispatcher:
    """
    Lightweight, direct stream processor for native tool calling and token emissions.
    Directly passes native thinking and conversational tokens while silently suppressing raw tool JSON blocks.
    """

    def __init__(self):
        self.full_content = ""
        self.suppress_tokens = False

    def handle_thinking(self, chunk: str) -> Optional[Dict[str, Any]]:
        """Emits thinking/reasoning events directly from provider."""
        if not chunk:
            return None
        return {"type": "thinking", "content": chunk}

    def handle_content(self, chunk: str) -> List[Dict[str, Any]]:
        """Processes content stream chunks and emits conversational tokens."""
        if not chunk:
            return []

        self.full_content += chunk

        # If content contains a tool call JSON, tag, or code block, suppress token emission
        stripped = self.full_content.lstrip()
        if (
            "```json" in self.full_content
            or "<tool_call" in self.full_content
            or "<tool" in self.full_content
            or stripped.startswith("```")
            or stripped.startswith("{")
            or stripped.startswith("<tool")
        ):
            self.suppress_tokens = True

        if self.suppress_tokens:
            return []

        # Clean tags and special tokens if any are embedded
        clean_chunk = re.sub(r"</?(?:think|thought|tool_call|tool_response|tool|tool_outputs?)>", "", chunk)
        clean_chunk = re.sub(r"<[｜|][\s\S]*?[｜|]>", "", clean_chunk)
        if clean_chunk:
            return [{"type": "token", "content": clean_chunk}]
        return []

    def extract_fallback_tools(self) -> List[Dict[str, Any]]:
        """Extracts tool calls from full content as fallback if native calling was not triggered."""
        return ToolCallParser.extract_tool_calls(self.full_content)

    @staticmethod
    def extract_clean_final_text(content: str) -> str:
        """Extracts clean conversational summary text without tool JSON or tags."""
        if not content:
            return ""
        cleaned = re.sub(r"<(?:think|thought|tool_call|tool_response|tool)>[\s\S]*?</(?:think|thought|tool_call|tool_response|tool)>", "", content)
        cleaned = re.sub(r"</?(?:think|thought|tool_call|tool_response|tool)>", "", cleaned)
        cleaned = re.sub(r"<[｜|][\s\S]*?[｜|]>", "", cleaned)
        cleaned = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", cleaned)
        cleaned = re.sub(r"^\s*\{[\s\S]*?\}\s*$", "", cleaned, flags=re.MULTILINE)
        return cleaned.strip()



# Backward compatibility alias
UniversalStreamNormalizer = StreamEventDispatcher
