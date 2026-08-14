from typing import Any, Dict, List

MAX_HISTORY_MESSAGES = 30


class ContextManager:
    """Manages conversation history and prevents context window overflow."""

    @staticmethod
    def prepare_messages(
        user_prompt: str,
        system_prompt: str,
        existing_messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Ensures system prompt is present, appends user prompt,
        and compacts old context if it exceeds MAX_HISTORY_MESSAGES.
        """
        # If history is empty, initialize with system prompt
        if not existing_messages:
            existing_messages.append({"role": "system", "content": system_prompt})
        elif existing_messages[0].get("role") != "system":
            existing_messages.insert(0, {"role": "system", "content": system_prompt})

        # Append new user prompt
        existing_messages.append({"role": "user", "content": user_prompt})

        # Truncate history if too long, while preserving system prompt at index 0
        if len(existing_messages) > MAX_HISTORY_MESSAGES:
            system_msg = existing_messages[0]
            recent_messages = existing_messages[-(MAX_HISTORY_MESSAGES - 1) :]
            existing_messages.clear()
            existing_messages.append(system_msg)
            existing_messages.extend(recent_messages)

        return existing_messages
