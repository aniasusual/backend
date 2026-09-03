"""
Tier 1 Context Squashing (Micro-Pruning).

Implements middle-truncation of historical tool outputs and sanitization of
reasoning blocks (<think>) to eliminate intra-turn token bloat.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from context.config import ContextConfig


class ContextSquasher:
    """
    Tier 1 Context Squashing:
    Middle-truncates historical tool results older than preserve_last_n_tools,
    prunes dead <think> reasoning blocks from prior turns, and eliminates token bloat.
    """

    @staticmethod
    def middle_truncate(text: str, max_chars: int = 500) -> str:
        """
        Truncates text using middle-truncation.
        Preserves the start (headers, commands) and the end (status, error messages).
        """
        if not text or len(text) <= max_chars:
            return text

        half = max_chars // 2
        omitted = len(text) - max_chars
        return f"{text[:half]}\n... [truncated {omitted} chars] ...\n{text[-half:]}"

    @staticmethod
    def sanitize_assistant_history(text: str) -> str:
        """
        Strips internal reasoning (<think> tags) and raw markdown code blocks from past turns
        so the assistant doesn't learn conversational code dumps.
        """
        if not text:
            return ""

        # Strip reasoning tags
        cleaned = re.sub(r"<(think|thought|tool_call|tool_response|tool_code)>[\s\S]*?</\1>", "", text)
        cleaned = re.sub(r"</?(?:think|thought|tool_call|tool_response|tool_code|tool|tools)>", "", cleaned)

        # Strip raw markdown code blocks (```...```)
        cleaned = re.sub(r"```[\w]*\s*\n?[\s\S]*?\n?```", "", cleaned)

        # Collapse excess newlines
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    @classmethod
    def apply_squash(
        cls,
        messages: List[Dict[str, Any]],
        config: ContextConfig,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Applies in-place squashing to messages:
        1. Identifies message-level tool turns.
        2. Preserves the last `preserve_last_n_tools` tool turns intact.
        3. Middle-truncates all older tool results.
        4. Prunes historical <think> blocks from previous turns.
        """
        if not messages:
            return messages, False

        # Identify indices of messages that represent tool results
        tool_turn_indices: List[int] = []
        for idx, m in enumerate(messages):
            role = m.get("role")
            content = m.get("content", "")
            if role == "tool":
                tool_turn_indices.append(idx)
            elif role == "user" and isinstance(content, str) and content.startswith("[Tool Result"):
                tool_turn_indices.append(idx)

        # If tool results don't exceed preserve_last_n_tools, nothing to truncate
        squashed_any = False
        cutoff_index = -1
        if len(tool_turn_indices) > config.preserve_last_n_tools:
            # Cutoff is the index of the tool turn right before the preserved tail
            cutoff_index = tool_turn_indices[-(config.preserve_last_n_tools + 1)]

        for idx, m in enumerate(messages):
            role = m.get("role")
            content = m.get("content", "")

            # 1. Middle-truncate older tool results
            if idx <= cutoff_index and idx in tool_turn_indices:
                if isinstance(content, str) and len(content) > config.truncation_length:
                    m["content"] = cls.middle_truncate(content, config.truncation_length)
                    squashed_any = True

            # 2. Prune <think> blocks from all assistant messages except the very last one
            if role == "assistant" and idx < len(messages) - 1:
                if isinstance(content, str) and ("<think>" in content or "<thought>" in content):
                    cleaned = cls.sanitize_assistant_history(content)
                    if cleaned != content:
                        m["content"] = cleaned
                        squashed_any = True

        return messages, squashed_any
