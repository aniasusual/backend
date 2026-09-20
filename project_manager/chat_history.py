"""
Lowkey Chat History Manager.

Handles persistence, rehydration, and validation of project-scoped chat history
stored in ~/.lowkey/projects/<project_name>/.lowkey_chat.json.

Guarantees context equivalence across application restarts by preserving both:
1. ui_events: High-fidelity visual stream for the frontend UI.
2. llm_messages: Exact structured turn history for the backend context engine.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


CHAT_FILENAME = ".lowkey_chat.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatHistoryManager:
    """
    Manages reading, writing, and validating .lowkey_chat.json per project.
    """

    @staticmethod
    def get_chat_file(project_path: str | Path) -> Path:
        return Path(project_path).resolve() / CHAT_FILENAME

    @classmethod
    def load_history(cls, project_path: str | Path) -> Dict[str, Any]:
        """
        Loads and validates the project's chat history.
        Returns a valid dict structure with 'turns' list.
        """
        chat_file = cls.get_chat_file(project_path)
        if not chat_file.exists():
            return {
                "version": 1,
                "project_name": Path(project_path).name,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "turns": [],
            }

        try:
            data = json.loads(chat_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Corrupted chat history format")
            if "turns" not in data or not isinstance(data["turns"], list):
                data["turns"] = []
            return data
        except Exception as e:
            print(f"[ChatHistory] Warning: Failed to read {chat_file}: {e}")
            return {
                "version": 1,
                "project_name": Path(project_path).name,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "turns": [],
            }

    @classmethod
    def save_turn(cls, project_path: str | Path, turn_data: Dict[str, Any]) -> None:
        """
        Atomically appends or updates a completed turn in .lowkey_chat.json.
        """
        chat_file = cls.get_chat_file(project_path)
        history = cls.load_history(project_path)

        turn_id = turn_data.get("turn_id")
        existing_idx = None
        for idx, t in enumerate(history["turns"]):
            if t.get("turn_id") == turn_id:
                existing_idx = idx
                break

        if existing_idx is not None:
            history["turns"][existing_idx] = turn_data
        else:
            history["turns"].append(turn_data)

        history["updated_at"] = _now_iso()

        # Atomic file write via tempfile to prevent partial writes during crashes
        chat_file.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = chat_file.parent
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
                json.dump(history, tf, indent=2, ensure_ascii=False)
                temp_file = Path(tf.name)
            os.replace(temp_file, chat_file)
        except Exception as e:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            raise IOError(f"Failed to write chat history to {chat_file}: {e}")

    @classmethod
    def get_ui_events(cls, project_path: str | Path) -> List[Dict[str, Any]]:
        """
        Reconstructs the full visual event stream for frontend rendering.
        Collapses past tool calls and thoughts by default so old turns stay tidy.
        """
        history = cls.load_history(project_path)
        events: List[Dict[str, Any]] = []

        for turn in history.get("turns", []):
            turn_events = turn.get("ui_events", [])
            for evt in turn_events:
                evt_copy = dict(evt)
                # Ensure past tools and thoughts are marked collapsed on rehydration
                if evt_copy.get("type") in ["tool_call", "tool_result", "thinking"]:
                    evt_copy["collapsed"] = True
                events.append(evt_copy)

        return events

    @classmethod
    def get_llm_messages(cls, project_path: str | Path) -> List[Dict[str, Any]]:
        """
        Reconstructs the backend session_messages list for ContextManager.prepare_messages.
        Prunes any dangling or unclosed tool calls to ensure 100% compliance with Ollama API.
        """
        history = cls.load_history(project_path)
        messages: List[Dict[str, Any]] = []

        for turn in history.get("turns", []):
            turn_msgs = turn.get("llm_messages", [])
            messages.extend(turn_msgs)

        return cls.prune_dangling_tool_calls(messages)

    @staticmethod
    def prune_dangling_tool_calls(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Crash recovery: Ollama returns a 400 Bad Request if an assistant message contains
        tool_calls without matching tool result messages immediately following it, or if
        an orphaned tool result message exists without a preceding assistant message.
        This prunes uncompleted assistant tool calls and orphaned tool results.
        """
        if not messages:
            return []

        cleaned: List[Dict[str, Any]] = []
        i = 0
        n = len(messages)

        while i < n:
            msg = messages[i]
            role = msg.get("role")

            if role == "assistant" and msg.get("tool_calls"):
                # Collect tool calls in this assistant message
                tool_calls = msg["tool_calls"]
                # Count subsequent tool messages
                j = i + 1
                tool_results_count = 0
                while j < n and messages[j].get("role") == "tool":
                    tool_results_count += 1
                    j += 1

                if tool_results_count >= len(tool_calls):
                    # Valid completed tool turn
                    cleaned.append(msg)
                    for k in range(i + 1, j):
                        cleaned.append(messages[k])
                    i = j
                    continue
                else:
                    # Dangling tool calls without results: strip tool_calls to make it a pure content message
                    content = msg.get("content", "")
                    if content and content.strip():
                        cleaned.append({"role": "assistant", "content": content})
                    i = j
                    continue
            elif role == "tool":
                # Orphaned tool message without preceding assistant tool call: prune it
                i += 1
                continue
            else:
                cleaned.append(msg)
                i += 1

        return cleaned

    @classmethod
    def clear_history(cls, project_path: str | Path) -> None:
        """
        Clears the chat history file for the project.
        """
        chat_file = cls.get_chat_file(project_path)
        if chat_file.exists():
            try:
                chat_file.unlink()
            except Exception as e:
                print(f"[ChatHistory] Warning: Failed to delete {chat_file}: {e}")
