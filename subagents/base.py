from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Any, Callable, Set, Dict


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
        **kwargs,
    ):
        self.sandbox_path = Path(sandbox_path).resolve() if sandbox_path else None
        self.model_name = model_name
        self.tool_registry = tool_registry
        self.event_callback = event_callback

    @property
    def allowed_tools(self) -> Set[str]:
        """Set of tool names this subagent is strictly permitted to call."""
        return set()

    @property
    def system_prompt(self) -> str:
        """Domain-specific system prompt for the subagent."""
        return ""


