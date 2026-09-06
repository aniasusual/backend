import logging
from pathlib import Path
from typing import Dict, Any, Optional, Set

from config.settings import DEFAULT_MODEL_ID
from subagents.base import BaseSubagent
from subagents.runner import SubagentRunner
from subagents.troubleshoot import (
    TROUBLESHOOT_SYSTEM_PROMPT,
    StackTraceParser,
    StaticTroubleshootAnalyzer,
)

logger = logging.getLogger(__name__)


class TroubleshootSubagent(BaseSubagent):
    """
    Specialized Diagnostic and Root Cause Analysis (RCA) Subagent.
    Inspired by Emergent's troubleshoot_agent_sonnet_4_5 in mono/cortex.

    Operates as an autonomous child agent loop with strictly read-only tools,
    investigating the workspace to identify root causes and generate surgical fixes.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = DEFAULT_MODEL_ID,
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Any] = None,
        max_iterations: int = 6,
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
        """Strictly read-only tools permitted for RCA investigation."""
        return {"read_file", "view_bulk", "grep_search", "lint_javascript", "glob_files"}

    @property
    def system_prompt(self) -> str:
        return TROUBLESHOOT_SYSTEM_PROMPT

    def diagnose_error(
        self,
        error_log: str,
        context_file: str = "",
        recent_actions: str = "",
    ) -> str:
        """
        Performs Root Cause Analysis (RCA) on error logs or stack traces.
        Fast-paths deterministic environmental issues (missing deps, port locks, CORS),
        and runs the autonomous read-only investigation loop for code/runtime defects.
        """
        if not error_log or not error_log.strip():
            return "Error: error_log parameter must not be empty."

        clean_log = StackTraceParser.strip_ansi(error_log).strip()

        # ── Fast-Path Deterministic Pre-Filters ───────────────────────
        fast_path = StackTraceParser.classify_fast_path(clean_log)
        if fast_path:
            return fast_path

        # ── Autonomous Child-Loop Investigation ──────────────────────
        file_loc = self._extract_file_location(clean_log, context_file)
        task_prompt = f"""Investigate the following error in the workspace:

ERROR LOG / STACK TRACE:
{clean_log}

RELEVANT FILE / LOCATION:
{file_loc if file_loc else 'Unknown - please locate using glob_files, grep_search, or file inspection'}

RECENT ACTIONS:
{recent_actions if recent_actions else 'None provided'}

Inspect the code around the failing location and produce the structured RCA report with exact replacement code for the main agent."""

        if self.tool_registry:
            try:
                runner = SubagentRunner(
                    name="troubleshoot_agent",
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
                    and "Root Cause Analysis" in report
                    and len(report.strip()) >= 50
                ):
                    return report
            except Exception as e:
                logger.warning(f"TroubleshootSubagent autonomous runner failed, using heuristic fallback: {e}")

        # ── Fallback Heuristic if Ollama is unreachable ──────────────
        return self._heuristic_fallback(clean_log, file_loc)

    def _heuristic_fallback(self, clean_log: str, file_loc: str) -> str:
        """Intelligent rule-based fallback when LLM child loop is unreachable."""
        return StaticTroubleshootAnalyzer.analyze(self.sandbox_path, clean_log, file_loc)

    def _extract_file_location(self, log: str, fallback_file: str = "") -> str:
        """Extracts the file path and line number from stack traces across platforms."""
        return StackTraceParser.extract_file_location(log, fallback_file)
