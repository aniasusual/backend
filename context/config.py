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
    "\n\n[Instruction: Directly execute tools (write_files, edit_file, read_file, mount_file, execute_command) "
    "to inspect and modify project files on disk. Do not output raw code blocks in chat.]"
)

RECENCY_ANCHOR_CONFIRMATION = (
    "\n\n[Instruction: You now have the user's response/confirmation. Immediately execute the appropriate write tools "
    "(write_files, write_file, edit_file, or execute_command) to implement the requested changes on disk. "
    "Do NOT output conversational acknowledgements without calling tools.]"
)

RECENCY_ANCHOR_ERROR = (
    "\n\n[Instruction: An error or bug was reported. Immediately inspect the relevant files or logs and execute tools "
    "(edit_file, write_file, insert_text, or execute_command) to diagnose and fix the issue on disk. "
    "Do not output raw code blocks in chat.]"
)

RECENCY_ANCHOR_CONVERSATIONAL = (
    "\n\n[Instruction: Respond directly and accurately to the user's question or message in chat. "
    "Do NOT invoke file-writing, editing, or terminal tools unless specifically requested by the user.]"
)

RECENCY_ANCHOR_FIRST_MESSAGE = (
    "\n\n[Project Context — First Turn]\n"
    "The project currently contains a placeholder starter, NOT the user's requested app:\n"
    "- `src/App.jsx`: Temporary welcome screen with `.crbn-*` CSS classes. You MUST completely "
    "overwrite this file with the actual application. Never keep, wrap, or extend the welcome markup.\n"
    "- `server/index.js`: Starter Express backend with mock CRUD routes and an in-memory data store. "
    "Replace or adapt these routes and data models to match the requested app.\n"
    "- `src/index.css`: Production design system with CSS variables (`:root`), glass cards, buttons, "
    "and form utilities. Reuse these tokens for consistent aesthetics. Discard `.crbn-*` placeholder styles.\n"
    "- `package.json`: Has react, react-dom, lucide-react, express, cors pre-installed.\n\n"
    "Start by inspecting the project structure, then build the requested application using write_files "
    "to create both frontend and backend in one atomic operation."
)


# ─────────────────────────────────────────────────────────────────────────────
# Continuity Alert Markers (CP-103.2, CP-106)
# ─────────────────────────────────────────────────────────────────────────────

ALERT_EVICTION_MARKER = "[Context System Alert: Historical logs pruned due to token budget caps.]"


