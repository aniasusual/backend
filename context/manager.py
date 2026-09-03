"""
Master Context Manager for Lowkey.

Orchestrates in-loop squashing, inter-turn preparation, and macro-compaction.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from context.config import (
    ContextConfig,
    RECENCY_ANCHOR_DEFAULT,
    RECENCY_ANCHOR_CONFIRMATION,
    RECENCY_ANCHOR_ERROR,
)
from context.estimator import TokenEstimator
from context.squasher import ContextSquasher
from context.compactor import ContextCompactor


class ContextManager:
    """
    Master Context Manager for Lowkey.
    Orchestrates in-loop squashing, inter-turn preparation, and macro-compaction.
    """

    @staticmethod
    def sanitize_assistant_text(text: str) -> str:
        """Sanitizes assistant text by removing thinking tags and markdown code blocks."""
        return ContextSquasher.sanitize_assistant_history(text)

    @staticmethod
    def compact_prior_turns(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Compacts past completed turns into clean (user, assistant) message pairs.
        Preserves questions asked via ask_human and files modified.
        """
        if not messages:
            return []

        compacted: List[Dict[str, Any]] = []
        current_user = None
        current_assistant_content: List[str] = []
        modified_files: List[str] = []
        inspected_files: List[str] = []
        asked_questions: List[str] = []
        invoked_actions: List[str] = []
        has_finish: bool = False
        finish_summary: str = ""

        def _finalize_turn():
            nonlocal current_assistant_content, modified_files, inspected_files
            nonlocal asked_questions, invoked_actions, has_finish, finish_summary

            raw_text = " ".join(current_assistant_content).strip()
            sanitized_text = ContextSquasher.sanitize_assistant_history(raw_text)

            parts = []
            if sanitized_text:
                parts.append(sanitized_text)
            if invoked_actions:
                parts.append(f"{'; '.join(invoked_actions)}.")
            if asked_questions:
                parts.append(f"Question asked: {asked_questions[-1]}")
            if modified_files:
                parts.append(f"Updated files: {', '.join(sorted(set(modified_files)))}.")
            elif inspected_files:
                parts.append(f"Inspected files: {', '.join(sorted(set(inspected_files)))}.")
            elif has_finish:
                parts.append(finish_summary or "Task finished.")

            final_text = "\n".join(parts) if parts else "Understood."
            compacted.append({"role": "user", "content": current_user})
            compacted.append({"role": "assistant", "content": final_text})

            current_assistant_content = []
            modified_files = []
            inspected_files = []
            asked_questions = []
            invoked_actions = []
            has_finish = False
            finish_summary = ""

        for m in messages:
            role = m.get("role")
            content = m.get("content", "")

            if role == "system":
                continue

            elif role == "user":
                if current_user:
                    _finalize_turn()
                clean_user = content.split("\n\n[Instruction:")[0].strip()
                current_user = clean_user

            elif role == "assistant":
                if content:
                    current_assistant_content.append(content)
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

                        if fn_name == "ask_human":
                            q = args.get("question") or args.get("prompt")
                            opts = args.get("options")
                            if q:
                                q_str = q
                                if opts and isinstance(opts, list):
                                    q_str += f" (Options: {', '.join(str(o) for o in opts)})"
                                asked_questions.append(q_str)
                        elif fn_name in ["invoke_design_agent", "design_agent"]:
                            invoked_actions.append("Applied design system tokens to src/index.css")
                        elif fn_name in ["invoke_troubleshoot_agent", "troubleshoot_agent"]:
                            invoked_actions.append("Diagnosed runtime issue with Troubleshoot subagent")
                        elif fn_name in ["invoke_vision_agent", "vision_agent"]:
                            invoked_actions.append("Audited UI design polish with Vision subagent")
                        elif fn_name in ["test_ui", "testing_agent", "ui_testing_subagent"]:
                            invoked_actions.append("Ran automated UI verification tests")
                        elif fn_name.startswith("invoke_"):
                            subagent_title = fn_name.replace("invoke_", "").replace("_", " ").title()
                            invoked_actions.append(f"Executed {subagent_title} subagent")
                        elif fn_name in ["execute_command", "run_background_command"]:
                            cmd = args.get("command", "")
                            if cmd:
                                invoked_actions.append(f"Executed command: {cmd}")
                        elif fn_name == "finish":
                            has_finish = True
                            if args.get("summary"):
                                finish_summary = args.get("summary")

                        file_path = args.get("file_path")
                        if file_path:
                            if fn_name in ["write_file", "edit_file", "insert_text"]:
                                modified_files.append(file_path)
                            elif fn_name == "read_file":
                                inspected_files.append(file_path)

                        batch_files = args.get("files")
                        if isinstance(batch_files, list):
                            for bf in batch_files:
                                if isinstance(bf, dict) and bf.get("file_path"):
                                    modified_files.append(bf["file_path"])

        if current_user:
            _finalize_turn()

        return compacted

    @classmethod
    def prepare_messages(
        cls,
        user_prompt: str,
        system_prompt: str,
        existing_messages: List[Dict[str, Any]],
        model_name: str = "qwen2.5-coder:14b",
    ) -> List[Dict[str, Any]]:
        """
        Prepares message history for a new user turn:
        1. Compacts prior completed turns into clean, code-free user/assistant pairs.
        2. Preserves in-flight questions asked via ask_human.
        3. Detects confirmations ("yes", "continue") or errors and injects targeted action anchors.
        4. Runs macro-compaction if total token estimate exceeds compact_threshold.
        """
        config = ContextConfig.for_model(model_name)

        # 1. Compact prior turns
        compacted_history = cls.compact_prior_turns(existing_messages)

        # 2. Rebuild message list with system prompt
        existing_messages.clear()
        existing_messages.append({"role": "system", "content": system_prompt})
        existing_messages.extend(compacted_history)

        # 3. Determine targeted recency anchor
        clean_prompt_lower = user_prompt.strip().lower()
        is_confirmation = clean_prompt_lower in [
            "yes", "y", "sure", "ok", "okay", "continue", "please continue", "proceed", "go ahead", "start", "do it"
        ]
        last_turn_had_question = bool(
            compacted_history and "Question asked:" in compacted_history[-1].get("content", "")
        )
        is_error = any(kw in clean_prompt_lower for kw in ["error", "fail", "failed", "crash", "syntaxerror", "exception"])

        if is_confirmation or last_turn_had_question:
            anchor = RECENCY_ANCHOR_CONFIRMATION
        elif is_error:
            anchor = RECENCY_ANCHOR_ERROR
        else:
            anchor = RECENCY_ANCHOR_DEFAULT

        anchored_user_prompt = f"{user_prompt.strip()}{anchor}"
        existing_messages.append({"role": "user", "content": anchored_user_prompt})

        # 4. Check if token count exceeds compact threshold (82%)
        total_tokens = TokenEstimator.estimate_total(existing_messages)
        compact_limit = int(config.context_window * config.compact_threshold)

        if total_tokens >= compact_limit and len(existing_messages) > 6:
            # Macro-compaction: Keep system prompt (index 0) and the last 4 messages intact
            system_msg = existing_messages[0]
            tail_messages = existing_messages[-4:]
            messages_to_summarize = existing_messages[1:-4]

            synthetic_analysis = ContextCompactor.generate_synthetic_head(messages_to_summarize)

            existing_messages.clear()
            existing_messages.append(system_msg)
            existing_messages.append({"role": "user", "content": synthetic_analysis})
            existing_messages.append({"role": "assistant", "content": "Understood. Proceeding with active task."})
            existing_messages.extend(tail_messages)

        # 5. Safety limit on message count
        if len(existing_messages) > config.max_history_messages:
            system_msg = existing_messages[0]
            recent_messages = existing_messages[-(config.max_history_messages - 1):]
            existing_messages.clear()
            existing_messages.append(system_msg)
            existing_messages.extend(recent_messages)

        return existing_messages

    @classmethod
    def maybe_squash(
        cls,
        messages: List[Dict[str, Any]],
        model_name: str = "qwen2.5-coder:14b",
        config: Optional[ContextConfig] = None,
    ) -> bool:
        """
        In-loop squashing executed inside CodingHarness before every Ollama call.
        Middle-truncates older tool results when total tokens exceed squash_threshold (70%)
        or when more than preserve_last_n_tools results have accumulated.
        """
        if not messages:
            return False

        if config is None:
            config = ContextConfig.for_model(model_name)

        total_tokens = TokenEstimator.estimate_total(messages)
        threshold_tokens = int(config.context_window * config.squash_threshold)

        # Trigger squashing if above threshold OR if many tool results have accumulated
        tool_count = sum(1 for m in messages if m.get("role") == "tool")
        should_squash = total_tokens >= threshold_tokens or tool_count > config.preserve_last_n_tools

        if should_squash:
            _, was_applied = ContextSquasher.apply_squash(messages, config)
            return was_applied

        return False
