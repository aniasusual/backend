"""
Tier 2 Auto-Compaction (Macro-Compaction).

Generates a structured, defensive <analysis> synthetic head when conversation
exceeds context threshold, preserving recent turns cleanly with Continuation Posture.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Set
from context.config import ALERT_EVICTION_MARKER


class ContextCompactor:
    """
    Tier 2 Macro-Compaction:
    Generates a structured, defensive <analysis> synthetic head when conversation
    exceeds context threshold, preserving the recent turns cleanly.
    """

    @staticmethod
    def generate_synthetic_head(messages_to_summarize: List[Dict[str, Any]]) -> str:
        """
        Summarizes old conversation turns into a structured analysis head.
        Uses defensive past-tense framing (e.g. 'User had requested...') and
        an explicit Continuation Posture footer to prevent rogue execution.
        """
        user_requests: List[str] = []
        completed_actions: List[str] = []
        modified_files: Set[str] = set()
        open_questions: List[str] = []

        for m in messages_to_summarize:
            role = m.get("role")
            content = m.get("content", "")

            if role == "user":
                clean_user = content
                if ALERT_EVICTION_MARKER in clean_user:
                    clean_user = clean_user.replace(ALERT_EVICTION_MARKER, "").strip()
                if "\n\n[Instruction:" in clean_user:
                    clean_user = clean_user.split("\n\n[Instruction:")[0].strip()
                if "\n\n[Project Context" in clean_user:
                    clean_user = clean_user.split("\n\n[Project Context")[0].strip()
                if clean_user and clean_user.lower() not in ["yes", "continue", "proceed", "sure"]:
                    if clean_user not in user_requests:
                        user_requests.append(clean_user)

            elif role == "assistant":
                if m.get("tool_calls"):
                    for tc in m["tool_calls"]:
                        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                        fn_name = fn.get("name", "")
                        args = fn.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}

                        if fn_name == "invoke_design_agent":
                            completed_actions.append("Initialized UI/UX design tokens in src/index.css")
                        elif fn_name == "invoke_troubleshoot_agent":
                            completed_actions.append("Diagnosed and resolved runtime errors")
                        elif fn_name == "invoke_vision_agent":
                            completed_actions.append("Performed UI layout & aesthetic audit")
                        elif fn_name == "invoke_testing_agent":
                            completed_actions.append("Ran automated browser UI tests")
                        elif fn_name == "invoke_code_reviewer_agent":
                            completed_actions.append("Audited code quality, security, and React/Express architecture")
                        elif fn_name.startswith("invoke_"):
                            completed_actions.append(f"Ran {fn_name.replace('invoke_', '').replace('_', ' ').title()} subagent")
                        elif fn_name in ["execute_command", "run_background_command"]:
                            cmd = args.get("command", "")
                            if cmd:
                                completed_actions.append(f"Executed `{cmd}`")
                        elif fn_name in ["write_file", "edit_file", "insert_text"]:
                            fp = args.get("file_path")
                            if fp:
                                modified_files.add(fp)
                        elif fn_name == "write_files":
                            for bf in args.get("files", []):
                                if isinstance(bf, dict) and bf.get("file_path"):
                                    modified_files.add(bf["file_path"])
                        elif fn_name == "ask_human":
                            q = args.get("question") or args.get("prompt")
                            if q:
                                open_questions.append(q)

        # Build structured analysis
        primary_intent = user_requests[0] if user_requests else "Full-stack application development"
        files_str = ", ".join(sorted(modified_files)) if modified_files else "None yet"

        lines = [
            "<analysis>",
            "## Previous Session Context",
            f"- Original User Request: {primary_intent}",
        ]

        if len(user_requests) > 1:
            lines.append("- Cumulative User Directives:")
            for req in user_requests[1:]:
                lines.append(f"  * {req}")

        if completed_actions:
            lines.append(f"- Actions Completed: {'; '.join(completed_actions)}")

        lines.append(f"- Files Modified on Disk: {files_str}")

        if open_questions:
            lines.append(f"- Last Question Resolved: {open_questions[-1]}")

        # Scan for verified milestones or persistent errors in messages_to_summarize chronologically
        from context.squasher import ContextSquasher

        unresolved_diagnostics: Dict[str, str] = {}
        achieved_milestones: List[str] = []

        for m in messages_to_summarize:
            role = m.get("role")
            content = str(m.get("content") or "")

            if role == "assistant":
                if "Failures / Unresolved Errors:" in content:
                    err_section = content.split("Failures / Unresolved Errors:")[1].split("\n\n")[0].strip()
                    for line in err_section.splitlines():
                        clean_line = line.strip().lstrip("- ")
                        if clean_line:
                            k_match = re.match(r"\[([^\]]+)\]", clean_line)
                            k = k_match.group(1) if k_match else clean_line
                            unresolved_diagnostics[k] = clean_line

                if "Milestones resolved:" in content:
                    ms_section = content.split("Milestones resolved:")[1].split("\n\n")[0].strip()
                    for ms in ms_section.split(";"):
                        clean_ms = ms.strip().rstrip(".")
                        if clean_ms and clean_ms not in achieved_milestones:
                            achieved_milestones.append(clean_ms)
                        matched = [
                            k for k in unresolved_diagnostics
                            if str(k).lower() in clean_ms.lower()
                            or ("test" in clean_ms.lower() and "test" in str(k).lower())
                            or ("lint" in clean_ms.lower() and "syntax" in str(k).lower())
                        ]
                        for k in matched:
                            unresolved_diagnostics.pop(k, None)

            elif role == "tool" or (role == "user" and content.startswith("[Tool Result")):
                tool_name = m.get("name", "")
                if not tool_name and content.startswith("[Tool Result for '"):
                    m_name = re.search(r"\[Tool Result for '([^']+)'\]", content)
                    if m_name:
                        tool_name = m_name.group(1)

                if ContextSquasher.is_success_milestone(content, tool_name):
                    milestone_text = (
                        "Tests/verification passed"
                        if "pass" in content.lower() or "test" in str(tool_name).lower()
                        else "Code syntax and execution validated"
                    )
                    if milestone_text not in achieved_milestones:
                        achieved_milestones.append(milestone_text)
                    # Resolve earlier matching failures
                    matched = [
                        k for k in unresolved_diagnostics
                        if k == tool_name
                        or ("test" in str(k).lower() and "test" in milestone_text.lower())
                        or ("lint" in str(k).lower() and "syntax" in milestone_text.lower())
                        or (str(k) in milestone_text or milestone_text in str(k))
                    ]
                    for k in matched:
                        unresolved_diagnostics.pop(k, None)
                else:
                    err = ContextSquasher.extract_tool_error_summary(content, tool_name)
                    if err:
                        key = tool_name or "tool"
                        unresolved_diagnostics[key] = f"[{key}] {err}"

        if achieved_milestones:
            lines.append(f"- Verified Session Milestones: {'; '.join(achieved_milestones)}")

        retained_errors = list(unresolved_diagnostics.values())
        if retained_errors:
            lines.append(f"- Persistent Diagnostics / Active Issues: {'; '.join(retained_errors[:3])}")
        # Strict Continuation Posture learned from Emergent case studies:
        lines.extend([
            "## Continuation Posture",
            "- The items above describe past completed context.",
            "- Do NOT execute unprompted background tasks or delete files.",
            "- Only perform actions directly commanded by the user's latest message.",
            "</analysis>",
        ])

        return "\n".join(lines)

