"""
YieldTool implementation.
Replicates Oh My Pi's task/yield-assembly.ts and src/tools/yield.ts.
Enforces that subagents conclude by delivering validated findings or explicit blockers.
"""

import json
from typing import Any, Dict, List, Optional, Union
from .schema_validator import validate_schema


class YieldTool:
    """
    Mandatory terminal reporting tool for subagents.
    Enforces contract deliverables, validates output schemas, and records incremental/terminal data.
    """

    def __init__(
        self,
        output_schema: Optional[Dict[str, Any]] = None,
        schema_mode: str = "permissive",
    ):
        self.output_schema = output_schema
        self.schema_mode = schema_mode.lower() if schema_mode else "permissive"
        self.called = False
        self.data: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.is_terminal = False
        self.validation_error: Optional[str] = None
        self.incremental_sections: Dict[str, Any] = {}

    def execute(
        self,
        data: Optional[Union[Dict[str, Any], str]] = None,
        type: Optional[Union[str, List[str]]] = None,
        error: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """
        Execute a yield call from the subagent.

        Parameters:
        - data: The structured payload or findings dictionary (or JSON string).
        - type: If provided as a list/string (other than 'result'), treats as incremental section.
        - error: Explicit blocker explanation if the agent is unable to complete the task.
        """
        # Handle case where LLM passes fields at root instead of under 'data'
        if data is None and kwargs:
            data = kwargs

        # Handle case where LLM passes stringified JSON in 'data'
        if isinstance(data, str):
            stripped = data.strip()
            if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        data = parsed
                    elif isinstance(parsed, list):
                        data = {"items": parsed}
                except Exception:
                    pass

        # 1. Error blocker reported
        if error:
            self.called = True
            self.error = str(error)
            self.is_terminal = True
            return f"Yield blocker recorded: {self.error}. Turn concluded."

        # 2. Incremental section recording
        if type and type != "result" and not (isinstance(type, list) and "result" in type):
            section_name = type if isinstance(type, str) else "-".join(str(s) for s in type)
            if data is not None:
                self.incremental_sections[section_name] = data
            return f"Incremental section '{section_name}' recorded. Continue working or perform terminal yield."

        # 3. Terminal deliverable
        self.called = True
        self.is_terminal = True
        terminal_payload = data if isinstance(data, dict) else ({"raw": data} if data is not None else {})

        # Merge incremental sections with terminal payload (terminal fields take precedence)
        self.data = {**self.incremental_sections, **terminal_payload}

        # 4. Schema validation
        if self.output_schema and self.data is not None:
            is_valid, val_err = validate_schema(self.data, self.output_schema)
            if not is_valid:
                self.validation_error = val_err
                if self.schema_mode == "strict":
                    self.called = False
                    self.is_terminal = False
                    return (
                        f"Yield rejected: Schema validation error: {val_err}. "
                        "You MUST correct your yield data payload to match the expected schema."
                    )
                else:
                    # Permissive mode: accept with warning
                    return f"Yield accepted with schema warning: {val_err}."

        return "Yield accepted. Subagent task concluded successfully."

    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema definition of this Yield tool."""
        data_prop: Dict[str, Any] = {
            "type": "object",
            "description": "Structured deliverable findings matching your required schema.",
        }
        if self.output_schema and isinstance(self.output_schema, dict):
            data_prop = dict(self.output_schema)
            data_prop["description"] = "Structured deliverable findings matching your required schema."

        return {
            "type": "function",
            "function": {
                "name": "yield",
                "description": "Mandatory tool to report your final deliverable, structured data, or blocker error.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data": data_prop,
                        "type": {
                            "type": "string",
                            "description": "Optional section name for incremental reporting.",
                        },
                        "error": {
                            "type": "string",
                            "description": "Explicit blocker error description if unable to complete the task.",
                        },
                    },
                },
            },
        }

    def get_result(self) -> Dict[str, Any]:
        """Return structured summary of the yield outcome."""
        return {
            "called": self.called,
            "data": self.data,
            "error": self.error,
            "validation_error": self.validation_error,
            "is_terminal": self.is_terminal,
        }
