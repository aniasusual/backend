import json
import re
from typing import Any, Dict, List, Optional

KNOWN_TOOLS = {
    "write_file",
    "write_files",
    "edit_file",
    "insert_text",
    "read_file",
    "view_bulk",
    "glob_files",
    "grep_search",
    "list_directory",
    "locate_files_by_pattern",
    "extract_signatures",
    "map_dependencies",
    "mount_file",
    "unmount_file",
    "close_file",
    "list_mounted_files",
    "lint_javascript",
    "get_assets",
    "ask_human",
    "finish",
    "invoke_design_agent",
    "invoke_troubleshoot_agent",
    "invoke_vision_agent",
    "invoke_testing_agent",
    "invoke_code_reviewer_agent",
    "execute_command",
    "run_background_command",
    "stop_background_command",
}


class ToolCallParser:
    """Lightweight, resilient fallback parser to extract tool calls from text across all model families."""

    @classmethod
    def extract_tool_calls(cls, text: str) -> List[Dict[str, Any]]:
        """Extracts valid tool calls from a raw text response string."""
        if not text or not text.strip():
            return []

        text = text.strip()

        # 1. Direct JSON parse (with strict=False to tolerate control characters / unescaped newlines)
        direct = cls._try_parse_json(text)
        if direct:
            res = cls._normalize_calls(direct)
            if res:
                return res

        # 2. Extract from markdown code blocks (```json ... ``` or ``` ... ```)
        for block in re.findall(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", text):
            parsed = cls._try_parse_json(block.strip())
            if parsed:
                res = cls._normalize_calls(parsed)
                if res:
                    return res

        # 3. Extract from <tool_call>...</tool_call> or <write_files>...</write_files> tags
        tag_match = re.search(r"<(tool_call|tool|write_files|write_file|edit_file|read_file|locate_files_by_pattern|extract_signatures|map_dependencies|mount_file|unmount_file|close_file|list_mounted_files|execute_command)>\s*([\s\S]*?)\s*</", text)
        if tag_match:
            tag_name = tag_match.group(1)
            parsed = cls._try_parse_json(tag_match.group(2).strip())
            if parsed:
                if isinstance(parsed, dict) and tag_name in KNOWN_TOOLS and not ("name" in parsed or "tool" in parsed or "action" in parsed or "function" in parsed):
                    return [{"name": tag_name, "arguments": parsed}]
                res = cls._normalize_calls(parsed)
                if res:
                    return res

        # 4. Embedded JSON object search
        calls = cls._find_embedded_json(text)
        if calls:
            res = cls._normalize_calls(calls)
            if res:
                return res

        return []

    @staticmethod
    def _try_parse_json(content: str) -> Optional[Any]:
        """Attempts standard and relaxed JSON parsing."""
        try:
            return json.loads(content, strict=False)
        except Exception:
            return None

    @classmethod
    def _normalize_calls(cls, parsed: Any) -> List[Dict[str, Any]]:
        """Converts raw parsed objects or lists into standardized list of tool call dicts."""
        if isinstance(parsed, list):
            results = []
            for item in parsed:
                norm = cls._normalize_single_call(item)
                if norm:
                    results.append(norm)
            return results
        elif isinstance(parsed, dict):
            norm = cls._normalize_single_call(parsed)
            if norm:
                return [norm]
        return []

    @classmethod
    def _normalize_single_call(cls, item: Any) -> Optional[Dict[str, Any]]:
        """Normalizes a single dict into standard {'name': ..., 'arguments': ...} format."""
        if not isinstance(item, dict):
            return None

        # 1. Extract name from common keys
        name = item.get("name") or item.get("tool") or item.get("action") or item.get("function")

        # 2. Check if a known tool name is the root key (e.g. {"write_file": {...}})
        if not name:
            for k in KNOWN_TOOLS:
                if k in item:
                    name = k
                    val = item[k]
                    args = val if isinstance(val, (dict, list, str)) else {}
                    return {"name": str(name), "arguments": args}

        if not name:
            return None

        # 3. Extract arguments
        if "arguments" in item and isinstance(item["arguments"], (dict, list, str)):
            args = item["arguments"]
        elif "parameters" in item and isinstance(item["parameters"], (dict, list, str)):
            args = item["parameters"]
        elif "args" in item and isinstance(item["args"], (dict, list, str)):
            args = item["args"]
        else:
            # Collect all other keys as arguments
            args = {k: v for k, v in item.items() if k not in ["name", "tool", "action", "function", "type"]}

        return {"name": str(name), "arguments": args}

    @classmethod
    def _find_embedded_json(cls, text: str) -> List[Dict[str, Any]]:
        """Finds balanced JSON objects containing tool identifiers."""
        results = []
        depth = 0
        start = -1
        for i, char in enumerate(text):
            if char == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    snippet = text[start : i + 1]
                    parsed = cls._try_parse_json(snippet)
                    if isinstance(parsed, dict):
                        norm = cls._normalize_single_call(parsed)
                        if norm:
                            results.append(norm)
                    start = -1
        return results


