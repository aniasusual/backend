"""
Autonomous Vision & UI/UX Aesthetic Expert Subagent.
Inspired by Emergent's design_reviewer_gemini_3_pro and vision_expert_agent_sonnet_4.
Operates as an autonomous child loop using SubagentRunner with scoped tools:
{"read_file", "grep_search", "view_bulk", "get_assets"}.
Evaluates layout balance, dark mode contrast, Google Font pairings, responsive grid breakpoints,
detects unstyled raw HTML elements, and curates CDN assets.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Set

from config.settings import DEFAULT_MODEL_ID
from subagents.base import BaseSubagent
from subagents.runner import SubagentRunner
from subagents.vision import VISION_EXPERT_SYSTEM_PROMPT, StaticVisionAnalyzer

logger = logging.getLogger(__name__)


class VisionExpertSubagent(BaseSubagent):
    """
    Autonomous Aesthetic & UI/UX Vision Expert Subagent.
    Inspired by Emergent's visual_evaluation_subagent / design critique loop.
    Audits visual hierarchy, color contrast ratios, spacing consistency,
    Google Font pairings, responsive grid breakpoints, and asset curation.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = DEFAULT_MODEL_ID,
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Any] = None,
        max_iterations: int = 5,
        **kwargs,
    ):
        super().__init__(
            sandbox_path=sandbox_path,
            model_name=model_name,
            tool_registry=tool_registry,
            event_callback=event_callback,
            **kwargs,
        )
        self.max_iterations = max_iterations

    @property
    def allowed_tools(self) -> Set[str]:
        """Strictly scoped tools permitted for visual design audit."""
        return {"read_file", "grep_search", "view_bulk", "get_assets"}

    @property
    def system_prompt(self) -> str:
        return VISION_EXPERT_SYSTEM_PROMPT

    def critique_ui(
        self,
        target_component_or_file: str = "",
        screenshot_base64: str = "",
        design_intent: str = "",
    ) -> str:
        """
        Conducts an autonomous multi-turn aesthetic and design system audit.
        Uses SubagentRunner to inspect workspace files and curate assets.
        Falls back to deterministic StaticVisionAnalyzer if the model runner encounters errors.
        """
        target_file = target_component_or_file.strip() if target_component_or_file else "src/App.jsx"
        intent_desc = design_intent.strip() if design_intent else "Modern High-End Web Application"

        task_description = f"""Please conduct a rigorous UI/UX visual aesthetic audit of the application.
Target Component/File: `{target_file}`
Design Intent: {intent_desc}

### Audit Directives:
1. Inspect the design system foundation (`src/index.css` and `index.html`) using `view_bulk` to verify Google Font pairings and dark mode theme variables.
2. Inspect `{target_file}` (and related UI components) using `read_file` or `grep_search` to evaluate:
   - Layout balance, padding consistency, and card spacing.
   - Dark mode contrast (WCAG AA compliance) and semantic tokens vs hardcoded hex.
   - Responsive grid breakpoints (`sm:`, `md:`, `lg:`).
   - Unstyled raw HTML elements (`<button>`, `<input>`, `<select>`) lacking hover/active transitions.
3. If placeholder images (`placeholder.com`, `picsum.photos`) or icons are detected, call `get_assets(query=...)` to retrieve verified Unsplash CDN URLs and Lucide icons.
4. Synthesize and return the final structured Vision & Aesthetic Review Report.
"""

        # ── Autonomous Child Runner Execution ────────────────────────
        try:
            runner = SubagentRunner(
                name="vision_subagent",
                system_prompt=self.system_prompt,
                allowed_tools=self.allowed_tools,
                model_name=self.model_name,
                max_iterations=self.max_iterations,
                tool_registry=self.tool_registry,
                event_callback=self.event_callback,
            )
            result = runner.run(task_description)

            # Check for non-empty meaningful conclusion
            if result and len(result.strip()) > 50 and "Vision & Aesthetic Review Report" in result:
                return result.strip()
            elif result and len(result.strip()) > 100 and "Overall Visual Quality Score" in result:
                return result.strip()
            else:
                logger.info("[VisionExpertSubagent] Runner output incomplete, using static analyzer fallback.")

        except Exception as e:
            logger.warning(f"[VisionExpertSubagent] Autonomous runner failed: {e}. Using deterministic static fallback.")

        # ── Resilient Heuristic Fallback ──────────────────────────────
        analysis = StaticVisionAnalyzer.analyze(
            sandbox_path=self.sandbox_path,
            target_component_or_file=target_file,
            design_intent=intent_desc,
        )
        return StaticVisionAnalyzer.generate_report(analysis, design_intent=intent_desc)
