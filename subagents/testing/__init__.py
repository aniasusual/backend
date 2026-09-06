"""
Testing subagent package providing SDET prompts, DOM observer, and Playwright session manager.
"""

from subagents.testing.prompts import (
    SDET_SYSTEM_PROMPT,
    FALLBACK_SMOKE_REPORT_TEMPLATE,
)
from subagents.testing.observer import DOMObserver
from subagents.testing.session import PlaywrightBrowserSession

__all__ = [
    "SDET_SYSTEM_PROMPT",
    "FALLBACK_SMOKE_REPORT_TEMPLATE",
    "DOMObserver",
    "PlaywrightBrowserSession",
]
