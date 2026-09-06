"""
Reviewer Subagent Package.
Provides autonomous senior-level code reviews and static security audits.
"""

from subagents.reviewer.prompts import CODE_REVIEWER_SYSTEM_PROMPT
from subagents.reviewer.scanner import StaticSecurityScanner

__all__ = [
    "CODE_REVIEWER_SYSTEM_PROMPT",
    "StaticSecurityScanner",
]
