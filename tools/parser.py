import json
import re
from typing import Any, Dict, List, Optional


class ToolCallParser:
    """Helper class to extract tool call payloads from LLM text responses."""

    @classmethod
    def extract_tool_calls(cls, text: str) -> List[Dict[str, Any]]:
        """Extracts all valid tool calls from a raw text response string."""
        if not text or not text.strip():
            return []

        # Strategy 1: Extract from <tool_call> ... </tool_call> tags
        calls = cls._from_tool_call_tags(text)
        if calls:
            return calls

        # Strategy 2: Extract from ```json ... ``` markdown blocks
        calls = cls._from_markdown_blocks(text)
        if calls:
            return calls

        # Strategy 3: Entire text is a single JSON object
        call = cls._from_full_text(text)
        if call:
            return [call]

        # Strategy 4: Find embedded JSON objects in text
        return cls._from_embedded_json(text)

    @staticmethod
    def _is_valid_tool_call(obj: Any) -> bool:
        return isinstance(obj, dict) and "name" in obj and "arguments" in obj

    @classmethod
    def _from_tool_call_tags(cls, text: str) -> List[Dict[str, Any]]:
        tool_calls = []
        tags = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
        for tag in tags:
            try:
                parsed = json.loads(tag.strip())
                if cls._is_valid_tool_call(parsed):
                    tool_calls.append(parsed)
                elif isinstance(parsed, list):
                    for item in parsed:
                        if cls._is_valid_tool_call(item):
                            tool_calls.append(item)
            except (json.JSONDecodeError, TypeError):
                pass
        return tool_calls

    @classmethod
    def _from_markdown_blocks(cls, text: str) -> List[Dict[str, Any]]:
        tool_calls = []
        # Match both ```json ... ``` and plain ``` ... ``` blocks
        json_blocks = re.findall(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        for block in json_blocks:
            try:
                parsed = json.loads(block.strip())
                if cls._is_valid_tool_call(parsed):
                    tool_calls.append(parsed)
                elif isinstance(parsed, list):
                    for item in parsed:
                        if cls._is_valid_tool_call(item):
                            tool_calls.append(item)
            except (json.JSONDecodeError, TypeError):
                pass
        return tool_calls

    @classmethod
    def _from_full_text(cls, text: str) -> Optional[Dict[str, Any]]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```\w*\n?", "", stripped)
            stripped = re.sub(r"\n?```$", "", stripped)
            stripped = stripped.strip()

        try:
            parsed = json.loads(stripped)
            if cls._is_valid_tool_call(parsed):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    @classmethod
    def _from_embedded_json(cls, text: str) -> List[Dict[str, Any]]:
        tool_calls = []
        brace_depth = 0
        start = None
        for i, char in enumerate(text):
            if char == "{":
                if brace_depth == 0:
                    start = i
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth == 0 and start is not None:
                    candidate = text[start : i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if cls._is_valid_tool_call(parsed):
                            tool_calls.append(parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass
                    start = None
        return tool_calls
