"""
Token Estimation Module.

Provides fast, accurate character-based token estimation for chat messages,
tool definitions, and conversational payloads with framing overhead.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Optional, Union


class TokenEstimator:
    """
    Fast and accurate character-based token estimator with message framing overhead.
    Derived from standard Byte-Pair Encoding heuristics (~3.7 chars per token for code/JSON).
    """

    CHARS_PER_TOKEN: float = 3.7
    MESSAGE_OVERHEAD_TOKENS: int = 4  # Standard chat format overhead (<|im_start|>role ... <|im_end|>)

    @classmethod
    def estimate_text(cls, text: Optional[Any]) -> int:
        """Estimates token count for a raw string or text-convertible object."""
        if text is None:
            return 0
        if isinstance(text, str):
            clean_text = text
        elif isinstance(text, (bytes, bytearray)):
            clean_text = text.decode("utf-8", errors="replace")
        else:
            clean_text = str(text)
        if not clean_text:
            return 0
        return max(1, math.ceil(len(clean_text) / cls.CHARS_PER_TOKEN))

    @classmethod
    def estimate_message(cls, message: Dict[str, Any]) -> int:
        """Estimates token count for a single structured chat message."""
        if not message or not isinstance(message, dict):
            return 0
        tokens = cls.MESSAGE_OVERHEAD_TOKENS

        content = message.get("content")
        if isinstance(content, str):
            tokens += cls.estimate_text(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    tokens += cls.estimate_text(block["text"])
                elif isinstance(block, str):
                    tokens += cls.estimate_text(block)
        elif content is not None:
            tokens += cls.estimate_text(content)

        # Message sender name (e.g. role == "tool" / function name)
        name = message.get("name")
        if name:
            tokens += cls.estimate_text(name)

        # Native thinking / reasoning block (DeepSeek-R1 / Ollama / Claude)
        thinking = message.get("thinking")
        if thinking:
            tokens += cls.estimate_text(thinking)

        # Account for tool calls if present
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                tokens += 8  # Tool call framing boundary tokens
                if not isinstance(tc, dict):
                    continue
                tc_id = tc.get("id")
                if tc_id:
                    tokens += cls.estimate_text(tc_id)
                fn = tc.get("function", {})
                if isinstance(fn, dict):
                    tokens += cls.estimate_text(fn.get("name", ""))
                    args = fn.get("arguments", "")
                    if isinstance(args, str):
                        tokens += cls.estimate_text(args)
                    elif isinstance(args, (dict, list)):
                        try:
                            tokens += cls.estimate_text(json.dumps(args, separators=(",", ":"), default=str))
                        except Exception:
                            tokens += cls.estimate_text(str(args))
                    elif args is not None:
                        tokens += cls.estimate_text(str(args))
                elif isinstance(fn, str):
                    tokens += cls.estimate_text(fn)

        return tokens

    @classmethod
    def estimate_schema(cls, schema: Dict[str, Any]) -> int:
        """Estimates token count for a single tool JSON schema."""
        if not schema or not isinstance(schema, dict):
            return 0
        try:
            dumped = json.dumps(schema, separators=(",", ":"), ensure_ascii=False, default=str)
            return cls.estimate_text(dumped) + 10  # Schema boundary framing overhead
        except Exception:
            return 0

    @classmethod
    def estimate_schemas(
        cls,
        schemas: Optional[Union[List[Dict[str, Any]], Dict[str, Any], Iterable[Dict[str, Any]]]],
    ) -> int:
        """
        Estimates total token count for tool JSON schemas.
        Supports:
        - List, tuple, set, or iterable of schema dicts
        - Dictionary mapping tool names to schema dicts: {tool_name: schema_dict}
        - A single tool schema dict passed directly
        """
        if not schemas or isinstance(schemas, (str, bytes)):
            return 0

        # Handle a single tool schema dict passed directly
        if isinstance(schemas, dict):
            is_single_schema = (
                ("type" in schemas and "function" in schemas)
                or ("name" in schemas and ("parameters" in schemas or "properties" in schemas or "description" in schemas))
            )
            if is_single_schema:
                return cls.estimate_schema(schemas)
            schema_iter = schemas.values()
        elif isinstance(schemas, (list, tuple, set)):
            schema_iter = schemas
        elif hasattr(schemas, "__iter__"):
            schema_iter = schemas
        else:
            return 0
        return sum(cls.estimate_schema(s) for s in schema_iter)

    @classmethod
    def estimate_virtual_ram(cls, mounted_ram: Optional[Dict[str, str]]) -> int:
        """Estimates token count for files actively mounted in Virtual RAM."""
        if not mounted_ram or not isinstance(mounted_ram, dict):
            return 0
        total = 0
        for path, content in mounted_ram.items():
            total += cls.estimate_text(f"--- FILE: {path} ---\n{content}\n")
        return total

    @classmethod
    def estimate_total(
        cls,
        messages: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = "",
        tools: Optional[Union[List[Dict[str, Any]], Dict[str, Any], Iterable[Dict[str, Any]]]] = None,
        virtual_ram: Optional[Dict[str, str]] = None,
        schemas: Optional[Union[List[Dict[str, Any]], Dict[str, Any], Iterable[Dict[str, Any]]]] = None,
    ) -> int:
        """Estimates total tokens across system prompt, active tool schemas, mounted Virtual RAM, and full message thread."""
        active_tools = tools if tools is not None else schemas
        total = 3  # Prime tokens (<|im_start|>assistant)

        msg_list: List[Dict[str, Any]] = []
        if messages:
            if isinstance(messages, (list, tuple)):
                msg_list = list(messages)
            elif hasattr(messages, "__iter__"):
                msg_list = list(messages)

        if system_prompt:
            # Avoid double-counting if system message is already present in messages
            already_has_system = any(isinstance(m, dict) and m.get("role") == "system" for m in msg_list)
            if not already_has_system:
                total += cls.estimate_text(system_prompt) + cls.MESSAGE_OVERHEAD_TOKENS

        if active_tools:
            total += cls.estimate_schemas(active_tools)

        if virtual_ram:
            # Avoid double-counting if virtual RAM register is already rendered in system_prompt or messages
            sys_text = system_prompt or ""
            already_rendered = (
                "[DYNAMIC ENVIRONMENT RAM REGISTER" in sys_text
                or any(
                    isinstance(m, dict) and "[DYNAMIC ENVIRONMENT RAM REGISTER" in str(m.get("content", ""))
                    for m in msg_list
                )
            )
            if not already_rendered:
                total += cls.estimate_virtual_ram(virtual_ram)

        for msg in msg_list:
            total += cls.estimate_message(msg)
        return total
