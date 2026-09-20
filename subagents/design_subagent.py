"""
Autonomous UI/UX Design Subagent.
Synthesizes user problem statements and explicit aesthetic preferences into bespoke,
production-grade design systems into `src/index.css` and feature-driven component blueprints.
Detects and strictly preserves existing styling frameworks (e.g. Tailwind CSS).
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Set

from config.settings import DEFAULT_MODEL_ID
from subagents.base import BaseSubagent
from subagents.runner import SubagentRunner
from subagents.design import (
    DESIGN_SYSTEM_PROMPT,
    detect_tailwind,
    parse_user_taste,
    generate_design_system_css,
    detect_archetype,
    format_topology_blueprint,
)

logger = logging.getLogger(__name__)


class DesignSubagent(BaseSubagent):
    """
    Autonomous Design Subagent (inspired by Emergent's design_agent_v1).
    Synthesizes problem statements into tailored, production-ready CSS design systems,
    Google Font pairings, dark mode glassmorphism tokens, and responsive UI layout blueprints.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = DEFAULT_MODEL_ID,
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Any] = None,
        max_iterations: int = 40,
        allowed_tools: Optional[Any] = None,
        **kwargs,
    ):
        super().__init__(
            sandbox_path=sandbox_path,
            model_name=model_name,
            tool_registry=tool_registry,
            event_callback=event_callback,
            allowed_tools=allowed_tools,
            **kwargs,
        )
        self.max_iterations = max_iterations

    @property
    def default_allowed_tools(self) -> Set[str]:
        """Default tools permitted for the autonomous design child loop."""
        return {"write_file", "get_assets", "read_file", "view_bulk"}

    @property
    def system_prompt(self) -> str:
        return DESIGN_SYSTEM_PROMPT

    def generate_layout_blueprint(
        self,
        problem_statement: str,
        app_type: str = "saas_app",
        theme_preference: str = "",
        auto_apply_css: bool = True,
    ) -> str:
        """
        Synthesizes the problem statement into a bespoke UI/UX design blueprint
        via an autonomous child-loop designer, ensuring design tokens are committed
        to src/index.css on disk while strictly preserving Tailwind directives.
        """
        is_tailwind, existing_css = detect_tailwind(self.sandbox_path)

        # ── Autonomous Child-Loop Execution ─────────────────────────
        if self.tool_registry:
            framework_note = (
                "Tailwind CSS is DETECTED in this project. You MUST preserve "
                "`@tailwind base; @tailwind components; @tailwind utilities;` at the top of src/index.css "
                "and encapsulate custom classes inside `@layer components { ... }`."
                if is_tailwind
                else "Vanilla CSS environment detected. Write standard modern CSS variables and utility classes."
            )

            task_prompt = f"""Design a bespoke modern UI/UX design system and component architecture for the following application:

APPLICATION GOAL / PROBLEM STATEMENT:
{problem_statement}

APPLICATION TYPE:
{app_type or 'Modern Web Application'}

USER TASTE / AESTHETIC PREFERENCE:
{theme_preference or 'Modern sleek dark mode with vibrant interactive accents'}

PROJECT ENVIRONMENT:
{framework_note}

Tasks to complete:
1. Call view_bulk(files=["package.json", "src/index.css"]) to inspect existing styles and dependencies.
2. (Optional) Call get_assets(query="...") to find curated Unsplash image CDN URLs and Lucide icon recommendations.
3. Call write_file(file_path="src/index.css", content="...") to write the complete bespoke design system into src/index.css (Google Fonts import, CSS variables, glassmorphic card utilities, button tokens, and strictly preserving @tailwind directives if applicable).
4. Return the structured UI/UX component blueprint tailored directly to this application's actual features."""

            try:
                runner = SubagentRunner(
                    name="design_agent",
                    system_prompt=self.system_prompt,
                    allowed_tools=self.allowed_tools,
                    model_name=self.model_name,
                    max_iterations=self.max_iterations,
                    tool_registry=self.tool_registry,
                    event_callback=self.event_callback,
                )
                report = runner.run(task_prompt)
                self.last_run_events = runner.last_run_events
                self.last_run_metrics = runner.last_run_metrics
                if (
                    report
                    and not report.startswith("Error:")
                    and not report.startswith("Subagent execution failed")
                    and len(report.strip()) >= 30
                ):
                    # Guarantee src/index.css exists on disk even if model forgot to call write_file
                    if auto_apply_css and self.sandbox_path:
                        self._ensure_baseline_css_on_disk(problem_statement, theme_preference)
                    return report
                else:
                    logger.info("[DesignSubagent] Runner output incomplete or failed, using heuristic fallback.")
            except Exception as e:
                logger.warning(f"DesignSubagent autonomous runner failed, using heuristic fallback: {e}")

        # ── Deterministic Heuristic Fallback ────────────────────────
        return self._heuristic_fallback(
            problem_statement=problem_statement,
            app_type=app_type,
            theme_preference=theme_preference,
            auto_apply_css=auto_apply_css,
        )

    def _ensure_baseline_css_on_disk(self, problem_statement: str, theme_preference: str = "") -> None:
        """Guarantees src/index.css is present on disk with valid design tokens without wiping Tailwind."""
        if not self.sandbox_path:
            return

        is_tailwind, existing_css = detect_tailwind(self.sandbox_path)
        css_file = self.sandbox_path / "src" / "index.css"

        # If file missing or too small or lacks essential variables, generate it
        current_content = css_file.read_text(encoding="utf-8", errors="ignore").strip() if css_file.exists() else ""
        if not css_file.exists() or len(current_content) < 50 or "--primary" not in current_content:
            css_file.parent.mkdir(parents=True, exist_ok=True)
            theme = parse_user_taste(problem_statement, theme_preference)
            content = generate_design_system_css(theme, is_tailwind=is_tailwind, existing_css=existing_css)
            css_file.write_text(content, encoding="utf-8")

    def _heuristic_fallback(
        self,
        problem_statement: str,
        app_type: str = "saas_app",
        theme_preference: str = "",
        auto_apply_css: bool = True,
    ) -> str:
        """Feature-driven deterministic fallback synthesizing tailored design tokens and architecture."""
        is_tailwind, existing_css = detect_tailwind(self.sandbox_path)

        if auto_apply_css and self.sandbox_path:
            self._ensure_baseline_css_on_disk(problem_statement, theme_preference)

        theme = parse_user_taste(problem_statement, theme_preference)
        archetype = detect_archetype(problem_statement, app_type)

        return format_topology_blueprint(
            archetype=archetype,
            theme=theme,
            problem_statement=problem_statement,
            app_type=app_type,
            is_tailwind=is_tailwind,
        )
