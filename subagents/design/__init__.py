"""
Design subagent package providing prompts, dynamic generators, and topology builders.
"""

from subagents.design.prompts import DESIGN_SYSTEM_PROMPT
from subagents.design.generator import (
    detect_tailwind,
    parse_user_taste,
    generate_design_system_css,
)
from subagents.design.topology import (
    detect_archetype,
    format_topology_blueprint,
)

__all__ = [
    "DESIGN_SYSTEM_PROMPT",
    "detect_tailwind",
    "parse_user_taste",
    "generate_design_system_css",
    "detect_archetype",
    "format_topology_blueprint",
]
