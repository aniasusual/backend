"""
Context Engine Configuration & Constants.

Defines runtime configuration thresholds, anchor directives, and token window defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config.models import get_model_context_window


@dataclass
class ContextConfig:
    """
    Configuration thresholds for in-loop squashing, compaction, and history limits.
    """
    context_window: int = 32768
    squash_threshold: float = 0.70       # Trigger in-loop tool squashing at 70% of context window
    compact_threshold: float = 0.82      # Trigger macro-compaction at 82% of context window
    preserve_last_n_tools: int = 3       # Keep the last N completed tool turns in full detail
    truncation_length: int = 500         # Max characters for middle-truncated tool outputs
    max_history_messages: int = 30       # Hard safety limit for total turn pairs

    @classmethod
    def for_model(cls, model_name: str) -> ContextConfig:
        """Constructs a ContextConfig with model-appropriate context window."""
        ctx_window = get_model_context_window(model_name)
        return cls(context_window=ctx_window)


# ─────────────────────────────────────────────────────────────────────────────
# Targeted Recency Anchors
# ─────────────────────────────────────────────────────────────────────────────

RECENCY_ANCHOR_DEFAULT = (
    "\n\n[Instruction: Directly execute tools (write_files, edit_file, read_file, execute_command) "
    "to inspect and modify project files on disk. Do not output raw code blocks in chat.]"
)

RECENCY_ANCHOR_CONFIRMATION = (
    "\n\n[Instruction: You now have the user's response/confirmation. Immediately execute the appropriate write tools "
    "(write_file or write_files) to implement the Express backend in server/index.js and React frontend in src/App.jsx. "
    "Do NOT output conversational acknowledgements without calling write tools.]"
)

RECENCY_ANCHOR_ERROR = (
    "\n\n[Instruction: An error or bug was reported. Immediately inspect the offending code and execute write tools "
    "(write_file, edit_file, or insert_text) to apply the fix on disk. Do not output raw code blocks in chat.]"
)
