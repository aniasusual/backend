import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, Set, List

from config.settings import DEFAULT_MODEL_ID
from subagents.base import BaseSubagent
from subagents.runner import SubagentRunner
from subagents.reviewer import CODE_REVIEWER_SYSTEM_PROMPT, StaticSecurityScanner

logger = logging.getLogger(__name__)


class CodeReviewerSubagent(BaseSubagent):
    """
    Autonomous Code Reviewer & Security Audit Subagent (inspired by Emergent's expert_opinion_agent_opus).
    Inspects workspace source files using read-only tools to verify code correctness,
    security posture, API error handling, and React performance.
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
        """Strictly read-only tools permitted for code audit."""
        return {"read_file", "view_bulk", "grep_search", "lint_javascript", "glob_files"}

    @property
    def system_prompt(self) -> str:
        return CODE_REVIEWER_SYSTEM_PROMPT

    def review_code(
        self,
        target_files: Any = "",
        focus_areas: Any = "",
    ) -> str:
        """
        Conducts an autonomous code review of target files or primary application code
        using an isolated child loop.
        """
        # Resolve target files across multi-file scope
        files_to_check = self._resolve_target_files(target_files)
        focus_str = ", ".join(focus_areas) if isinstance(focus_areas, (list, tuple)) else str(focus_areas or "")

        # ── Autonomous Child-Loop Execution ─────────────────────────
        if self.tool_registry:
            task_prompt = f"""Conduct a comprehensive senior-level code review and security audit of the application code:

TARGET FILES TO AUDIT:
{', '.join(files_to_check) if files_to_check else 'Inspect discovered source files across src/ and server/'}

FOCUS AREAS:
{focus_str if focus_str else 'Correctness, security vulnerabilities, Express error handling, React best practices, and runtime safety'}

Instructions:
1. Use glob_files, read_file, or view_bulk to discover and read code across components, routes, and server files.
2. Use lint_javascript to check for syntax errors or lint warnings on JavaScript/JSX files.
3. Check for security issues (hardcoded credentials, unhandled API rejections, SQL/shell injection).
4. Return the structured Code Review & Security Audit report with score and surgical fixes."""

            try:
                runner = SubagentRunner(
                    name="code_reviewer_agent",
                    system_prompt=self.system_prompt,
                    allowed_tools=self.allowed_tools,
                    model_name=self.model_name,
                    max_iterations=self.max_iterations,
                    tool_registry=self.tool_registry,
                    event_callback=self.event_callback,
                )
                report = runner.run(task_prompt)
                if (
                    report
                    and not report.startswith("Error:")
                    and not report.startswith("Subagent execution failed")
                    and ("Code Review" in report or "Code Quality Score" in report)
                    and len(report.strip()) >= 50
                ):
                    return report
            except Exception as e:
                logger.warning(f"CodeReviewerSubagent autonomous runner failed, using heuristic fallback: {e}")

        # ── Deterministic Heuristic Fallback ────────────────────────
        return self._heuristic_fallback(files_to_check, focus_str)

    def _resolve_target_files(self, target_files: Any) -> List[str]:
        """Resolves target files from argument string, list, or automatically discovers key app files."""
        if target_files:
            if isinstance(target_files, (list, tuple)):
                candidates = [str(f).strip() for f in target_files if str(f).strip()]
                if candidates:
                    return candidates
            elif isinstance(target_files, str):
                target_files = target_files.strip()
                if target_files.startswith("[") and target_files.endswith("]"):
                    try:
                        parsed = json.loads(target_files)
                        if isinstance(parsed, list):
                            candidates = [str(f).strip() for f in parsed if str(f).strip()]
                            if candidates:
                                return candidates
                    except Exception:
                        pass
                candidates = [f.strip() for f in re.split(r"[,;\s]+", target_files) if f.strip()]
                if candidates:
                    return candidates

        # Multi-file discovery across src/ and server/
        return StaticSecurityScanner.discover_code_files(self.sandbox_path)

    def _heuristic_fallback(self, files: List[str], focus_areas: str) -> str:
        """Deterministic static pattern audit used when LLM runner is unreachable."""
        findings, score = StaticSecurityScanner.scan(self.sandbox_path, files, focus_areas)
        return StaticSecurityScanner.generate_report(files, findings, score)
