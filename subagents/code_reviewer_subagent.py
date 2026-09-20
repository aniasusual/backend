import json
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, Set, List

from config.settings import DEFAULT_MODEL_ID
from subagents.base import BaseSubagent
from subagents.runner import SubagentRunner
from subagents.reviewer import (
    CODE_REVIEWER_SYSTEM_PROMPT,
    StaticSecurityScanner,
    ReviewFinding,
    ReviewAuditReport,
)

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
        self.last_report: Optional[ReviewAuditReport] = None

    @property
    def default_allowed_tools(self) -> Set[str]:
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

        # ── Pre-Flight Deterministic Static Scan ────────────────────
        # Run static scanner first (<10ms) to provide actionable, line-numbered leads for the LLM
        preflight_findings, preflight_score = StaticSecurityScanner.scan_structured(
            self.sandbox_path, files_to_check, focus_str
        )

        preflight_leads_block = ""
        if preflight_findings:
            leads = []
            for f in preflight_findings:
                loc = f"{f.file_path}:{f.line_number}" if f.line_number else f.file_path
                snippet = f' (Code: "{f.code_snippet}")' if f.code_snippet else ""
                leads.append(f"- [{f.severity.value}] {loc}: {f.description}{snippet}")
            preflight_leads_block = (
                "\n\nPRE-FLIGHT STATIC SCANNER LEADS (Inspect and verify these suspect locations):\n"
                + "\n".join(leads)
                + "\n(Deep-dive these locations using read_file to verify context, eliminate false positives, and formulate surgical replacement code)."
            )

        # ── Autonomous Child-Loop Execution ─────────────────────────
        if self.tool_registry:
            task_prompt = f"""Conduct a senior-level code review and security audit:

TARGET FILES:
{', '.join(files_to_check) if files_to_check else 'Inspect discovered source files across src/ and server/'}

FOCUS AREAS:
{focus_str if focus_str else 'Correctness, security vulnerabilities, Express error handling, React best practices, and runtime safety'}{preflight_leads_block}

Inspect the files, verify pre-flight leads, and return the structured Code Review & Security Audit report with score and surgical fixes."""

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
                self.last_run_events = runner.last_run_events
                self.last_run_metrics = runner.last_run_metrics
                if (
                    report
                    and not report.startswith("Error:")
                    and not report.startswith("Subagent execution failed")
                    and len(report.strip()) >= 30
                ):
                    self.last_report = ReviewAuditReport.from_markdown(report, files_to_check)
                    return report
            except Exception as e:
                logger.warning(f"CodeReviewerSubagent autonomous runner failed, using heuristic fallback: {e}")

        # ── Deterministic Heuristic Fallback ────────────────────────
        return self._heuristic_fallback(files_to_check, focus_str, preflight_findings, preflight_score)

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

    def _heuristic_fallback(
        self,
        files: List[str],
        focus_areas: str,
        preflight_findings: Optional[List[ReviewFinding]] = None,
        preflight_score: Optional[int] = None,
    ) -> str:
        """Deterministic static pattern audit used when LLM runner is unreachable."""
        findings = preflight_findings
        score = preflight_score
        if findings is None or score is None:
            findings, score = StaticSecurityScanner.scan_structured(self.sandbox_path, files, focus_areas)

        legacy_findings, legacy_score = StaticSecurityScanner.scan(self.sandbox_path, files, focus_areas)
        report_text = StaticSecurityScanner.generate_report(files, legacy_findings, legacy_score)
        self.last_report = ReviewAuditReport.from_markdown(report_text, files)
        return report_text
