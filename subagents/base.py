from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Any, Callable, Set, Dict, List


from config.settings import DEFAULT_MODEL_ID


class BaseSubagent(ABC):
    """
    Abstract base class for all specialized domain subagents.
    Provides standard sandbox context, tool scoping, and execution interface.
    """

    def __init__(
        self,
        sandbox_path: Optional[Path] = None,
        model_name: str = DEFAULT_MODEL_ID,
        tool_registry: Optional[Any] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        allowed_tools: Optional[Any] = None,
        **kwargs,
    ):
        self.sandbox_path = Path(sandbox_path).resolve() if sandbox_path else None
        self.model_name = model_name
        self.tool_registry = tool_registry
        self.event_callback = event_callback
        self.last_run_events: List[Dict[str, Any]] = []
        self.last_run_metrics: Dict[str, Any] = {}
        self._custom_allowed_tools: Optional[Set[str]] = self._normalize_tool_set(allowed_tools)

    @staticmethod
    def _normalize_tool_set(tools: Optional[Any]) -> Optional[Set[str]]:
        if tools is None:
            return None
        if isinstance(tools, str):
            return {t.strip() for t in tools.split(",") if t.strip()}
        return set(tools)

    @property
    def default_allowed_tools(self) -> Set[str]:
        """Default set of tool names permitted for this subagent type."""
        return set()

    @property
    def allowed_tools(self) -> Set[str]:
        """Set of tool names this subagent is strictly permitted to call."""
        if self._custom_allowed_tools is not None:
            return self._custom_allowed_tools
        return self.default_allowed_tools

    @allowed_tools.setter
    def allowed_tools(self, tools: Optional[Any]) -> None:
        """Allows dynamic override or mutation of allowed tools at runtime."""
        self._custom_allowed_tools = self._normalize_tool_set(tools)

    @property
    def system_prompt(self) -> str:
        """Domain-specific system prompt for the subagent."""
        return ""


