"""
Context Engine Configuration & Constants.

Defines runtime configuration thresholds and token window defaults.
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
# Continuity Alert Markers (CP-103.2, CP-106)
# ─────────────────────────────────────────────────────────────────────────────

ALERT_EVICTION_MARKER = "[Context System Alert: Historical logs pruned due to token budget caps.]"


