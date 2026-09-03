from typing import List, Optional, Callable


class InteractionTools:
    """
    Dedicated handler for structured human-in-the-loop interaction (clarifying questions,
    option selection chips) and task lifecycle finalization (structured summaries, next steps).
    """

    def __init__(self, event_callback: Optional[Callable[[dict], None]] = None):
        self.event_callback = event_callback

    def ask_human(self, question: str, options: Optional[List[str]] = None) -> str:
        """Ask the human user a clarifying question or present multiple design/architecture options.

        Args:
            question: The question or clarification prompt to ask the user.
            options: Optional list of selectable choice strings (e.g. ['Tailwind CSS', 'Vanilla CSS', 'Dark Mode']).

        Returns:
            A formatted acknowledgement indicating the question was dispatched to the user.
        """
        if not question or not question.strip():
            return "Error: question parameter must not be empty."

        clean_question = question.strip()
        opts_list = options if isinstance(options, list) else []

        payload = {
            "type": "ask_human",
            "question": clean_question,
            "options": opts_list,
        }

        if self.event_callback:
            self.event_callback(payload)

        formatted = f"❓ [Question sent to user]: {clean_question}"
        if opts_list:
            formatted += "\nOptions provided:\n" + "\n".join(f"  - {opt}" for opt in opts_list)

        return formatted

    def finish(self, summary: str, next_steps: Optional[str] = None) -> str:
        """Conclude the current task and provide a structured summary of accomplishments and next steps.

        Args:
            summary: Comprehensive summary of all files created/edited, features implemented, and verification results.
            next_steps: Optional guidance on how to run, test, or extend the app.

        Returns:
            A formatted completion confirmation.
        """
        if not summary or not summary.strip():
            return "Error: summary parameter must not be empty."

        clean_summary = summary.strip()
        clean_next = next_steps.strip() if next_steps else None

        payload = {
            "type": "task_finished",
            "summary": clean_summary,
            "next_steps": clean_next,
        }

        if self.event_callback:
            self.event_callback(payload)

        res = f"🎉 [Task Completed Successfully]\n\n**Summary:**\n{clean_summary}"
        if clean_next:
            res += f"\n\n**Next Steps:**\n{clean_next}"

        return res
