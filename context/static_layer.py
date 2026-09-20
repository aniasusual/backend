"""
Static Layer Management & Repository Rules Discovery.

Implements [CP-101.1] from the Dynamic Context Management Specification:
1. Pinned identity management.
2. Dynamic discovery of repository manifestos and rule files (.agentrules, AGENTS.md, .cursorrules, CLAUDE.md, README.md).
3. Strict token budgeting (< 1,500 tokens) with clean line-boundary truncation.
4. Clean markdown framing for the Static Layer system prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from context.estimator import TokenEstimator


class StaticLayerManager:
    """
    Manages Static Layer identity and project-specific structural directives.
    Discovers project rule files and binds them to the system prompt within a bounded token budget.
    """

    RULE_FILENAMES: List[str] = [
        ".agentrules",
        "AGENTS.md",
        ".cursorrules",
        "CLAUDE.md",
        "README.md",
        "readme.md",
    ]

    MAX_RULES_TOKENS: int = 1500
    TRUNCATION_NOTICE: str = "\n\n[Notice: Rules truncated — exceeded 1,500 token limit]"

    @classmethod
    def discover_project_rules(
        cls,
        project_root: Optional[str | Path],
        max_tokens: int = MAX_RULES_TOKENS,
    ) -> Optional[Dict[str, Any]]:
        """
        Discovers project instruction files in priority order:
        1. .agentrules
        2. AGENTS.md
        3. .cursorrules
        4. CLAUDE.md
        5. README.md (or readme.md)

        Enforces a strict token ceiling (default 1,500 tokens). If content exceeds the ceiling,
        it is truncated at line boundaries and annotated with a notice.
        """
        if not project_root:
            return None

        root_path = Path(project_root).resolve()
        if not root_path.exists() or not root_path.is_dir():
            return None

        for filename in cls.RULE_FILENAMES:
            candidate_file = root_path / filename
            if candidate_file.is_file():
                try:
                    content = candidate_file.read_text(encoding="utf-8", errors="replace").strip()
                    if not content:
                        continue

                    est_tokens = TokenEstimator.estimate_text(content)
                    is_truncated = False

                    if est_tokens > max_tokens:
                        is_truncated = True
                        notice_tokens = TokenEstimator.estimate_text(cls.TRUNCATION_NOTICE)
                        budget_tokens = max(10, max_tokens - notice_tokens)
                        budget_chars = int(budget_tokens * TokenEstimator.CHARS_PER_TOKEN)

                        # Truncate at nearest newline within budget
                        slice_point = content[:budget_chars].rfind("\n")
                        if slice_point > 0:
                            content = content[:slice_point].rstrip() + cls.TRUNCATION_NOTICE
                        else:
                            content = content[:budget_chars].rstrip() + cls.TRUNCATION_NOTICE

                        est_tokens = TokenEstimator.estimate_text(content)

                    return {
                        "file_name": filename,
                        "file_path": str(candidate_file),
                        "content": content,
                        "tokens": est_tokens,
                        "truncated": is_truncated,
                    }
                except Exception as e:
                    print(f"[StaticLayerManager] Error reading {candidate_file}: {e}")
                    continue

        return None

    @classmethod
    def format_rules_block(cls, rule_info: Optional[Dict[str, Any]]) -> str:
        """Formats discovered project rules into a standardized markdown section."""
        if not rule_info or not rule_info.get("content"):
            return ""

        file_name = rule_info.get("file_name", "project rules")
        content = rule_info["content"]
        return f"\n\n## Repository Directives & Guidelines ({file_name})\n{content}"

    @classmethod
    def build_static_prompt(
        cls,
        base_prompt: str,
        project_root: Optional[str | Path] = None,
        runtime_context: Optional[str] = None,
        reasoning_fallback: Optional[str] = None,
        max_rules_tokens: int = MAX_RULES_TOKENS,
    ) -> str:
        """
        Assembles the complete Static Layer prompt:
        1. Pinned base system prompt (identity, environment rules).
        2. Discovered repository directives (.agentrules, AGENTS.md) bounded to max_rules_tokens.
        3. Active runtime dev server ports/URLs.
        4. Tool calling fallback protocol (for reasoning/non-native models).
        """
        sections = [base_prompt.rstrip()]

        rule_info = cls.discover_project_rules(project_root, max_tokens=max_rules_tokens)
        if rule_info:
            rules_block = cls.format_rules_block(rule_info)
            if rules_block:
                sections.append(rules_block.strip())

        if runtime_context and runtime_context.strip():
            sections.append(runtime_context.strip())

        if reasoning_fallback and reasoning_fallback.strip():
            sections.append(reasoning_fallback.strip())

        return "\n\n".join(sections)
