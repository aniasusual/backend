"""
Tier 2 Auto-Compaction (Macro-Compaction).

Generates a structured, defensive <analysis> synthetic head when conversation
exceeds context threshold, preserving recent turns cleanly with Continuation Posture.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Set


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
                clean_user = content.split("\n\n[Instruction:")[0].strip()
                if clean_user and clean_user.lower() not in ["yes", "continue", "proceed", "sure"]:
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

        if completed_actions:
            lines.append(f"- Actions Completed: {'; '.join(completed_actions)}")

        lines.append(f"- Files Modified on Disk: {files_str}")

        if open_questions:
            lines.append(f"- Last Question Resolved: {open_questions[-1]}")

        # Strict Continuation Posture learned from Emergent case studies:
        lines.extend([
            "## Continuation Posture",
            "- The items above describe past completed context.",
            "- Do NOT execute unprompted background tasks or delete files.",
            "- Only perform actions directly commanded by the user's latest message.",
            "</analysis>",
        ])

        return "\n".join(lines)
