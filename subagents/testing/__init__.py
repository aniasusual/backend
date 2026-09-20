"""
Testing subagent package providing SDET prompts, tool schemas, DOM observer, and Playwright session manager.
"""

from subagents.testing.prompts import (
    SDET_SYSTEM_PROMPT,
    BROWSER_TOOL_SCHEMAS,
)
from subagents.testing.observer import DOMObserver
from subagents.testing.session import PlaywrightBrowserSession

__all__ = [
    "SDET_SYSTEM_PROMPT",
    "BROWSER_TOOL_SCHEMAS",
    "DOMObserver",
    "PlaywrightBrowserSession",
]
