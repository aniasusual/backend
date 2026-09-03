"""
Token Estimation Module.

Provides fast, accurate character-based token estimation for chat messages,
tool definitions, and conversational payloads with framing overhead.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional


class TokenEstimator:
    """
    Fast and accurate character-based token estimator with message framing overhead.
    Derived from standard Byte-Pair Encoding heuristics (~3.7 chars per token for code/JSON).
    """

    CHARS_PER_TOKEN: float = 3.7
    MESSAGE_OVERHEAD_TOKENS: int = 4  # Standard chat format overhead (<|im_start|>role ... <|im_end|>)

    @classmethod
    def estimate_text(cls, text: Optional[str]) -> int:
        """Estimates token count for a raw string."""
        if not text:
            return 0
        return max(1, math.ceil(len(text) / cls.CHARS_PER_TOKEN))

    @classmethod
    def estimate_message(cls, message: Dict[str, Any]) -> int:
        """Estimates token count for a single structured chat message."""
        tokens = cls.MESSAGE_OVERHEAD_TOKENS

        content = message.get("content")
        if isinstance(content, str):
            tokens += cls.estimate_text(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    tokens += cls.estimate_text(block["text"])

        # Account for tool calls if present
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                tokens += 8  # Tool call framing boundary tokens
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                tokens += cls.estimate_text(fn.get("name", ""))
                args = fn.get("arguments", "")
                if isinstance(args, str):
                    tokens += cls.estimate_text(args)
                elif isinstance(args, dict):
                    tokens += cls.estimate_text(json.dumps(args))

        return tokens

    @classmethod
    def estimate_total(cls, messages: List[Dict[str, Any]], system_prompt: str = "") -> int:
        """Estimates total tokens across system prompt and full message thread."""
        total = 3  # Prime tokens (<|im_start|>assistant)
        if system_prompt:
            total += cls.estimate_text(system_prompt) + cls.MESSAGE_OVERHEAD_TOKENS
        for msg in messages:
            total += cls.estimate_message(msg)
        return total
